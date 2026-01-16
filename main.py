from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import ccxt
import pandas as pd
from datetime import datetime
import jwt

# ------------------ JWT CONFIG ------------------
SECRET_KEY = "SIMONS_SUPER_SECRET_KEY"
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ------------------ APP INIT ------------------
app = FastAPI(title="Simons Trading API")

# ------------------ CORS ------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ FAKE DATABASE ------------------
users_db = {}

# ------------------ MODELS ------------------
class SignupRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

# ------------------ AUTH ROUTES ------------------
@app.post("/signup")
def signup(data: SignupRequest):
    if data.email in users_db:
        raise HTTPException(status_code=400, detail="User already exists")

    users_db[data.email] = {
        "username": data.username,
        "email": data.email,
        "password": data.password
    }

    return {"message": "Account created successfully"}

@app.post("/login")
def login(data: LoginRequest):
    user = users_db.get(data.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Invalid password")

    # JWT TOKEN CREATE
    payload = {
        "sub": user["email"],
        "username": user["username"]
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "token": token,
        "user": {
            "username": user["username"],
            "email": user["email"]
        }
    }

# ------------------ TOKEN VERIFY ROUTE ------------------
@app.get("/verify-token")
def verify_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {
            "status": "ok",
            "user": {
                "email": payload.get("sub"),
                "username": payload.get("username")
            }
        }
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

# ------------------ EXCHANGE SETUP ------------------
exchange = ccxt.kraken({'enableRateLimit': True})

@app.get("/")
def read_root():
    return {"message": "Simons Trading API is running!", "status": "online"}

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/market/{symbol}")
async def get_market_data(symbol: str, timeframe: str = "1h", limit: int = 100):
    try:
        formatted_symbol = symbol.replace("-", "/")

        ohlcv = exchange.fetch_ohlcv(formatted_symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        df['mean'] = df['close'].rolling(window=20).mean()
        df['std'] = df['close'].rolling(window=20).std()
        df['zscore'] = (df['close'] - df['mean']) / df['std']

        ticker = exchange.fetch_ticker(formatted_symbol)

        return {
            "symbol": formatted_symbol,
            "currentPrice": ticker['last'],
            "change24h": ticker['percentage'],
            "volume24h": ticker['quoteVolume'],
            "high24h": ticker['high'],
            "low24h": ticker['low'],
            "zscore": float(df['zscore'].iloc[-1]) if not df['zscore'].isna().iloc[-1] else 0,
            "volatility": float(df['std'].iloc[-1]) if not df['std'].isna().iloc[-1] else 0,
            "signal": "LONG" if df['zscore'].iloc[-1] < -2 else "SHORT" if df['zscore'].iloc[-1] > 2 else "NEUTRAL",
            "chartData": df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            .tail(50).to_dict('records')
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orderbook/{symbol}")
async def get_orderbook(symbol: str, limit: int = 20):
    try:
        formatted_symbol = symbol.replace("-", "/")
        orderbook = exchange.fetch_order_book(formatted_symbol, limit=limit)

        return {
            "symbol": formatted_symbol,
            "bids": [{"price": b[0], "size": b[1]} for b in orderbook['bids'][:limit]],
            "asks": [{"price": a[0], "size": a[1]} for a in orderbook['asks'][:limit]],
            "timestamp": orderbook['timestamp']
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
