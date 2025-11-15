import os
import hashlib
import time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from database import db, create_document, get_documents
from bson.objectid import ObjectId

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBasic()

# Simple rate limit / DDoS throttle (per IP)
RATE_LIMIT_WINDOW_SEC = 10
RATE_LIMIT_MAX_REQUESTS = 50
_ip_hits = {}

@app.middleware("http")
async def throttle_middleware(request: Request, call_next):
    try:
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        hits = _ip_hits.get(ip, [])
        hits = [t for t in hits if now - t < RATE_LIMIT_WINDOW_SEC]
        hits.append(now)
        _ip_hits[ip] = hits
        if len(hits) > RATE_LIMIT_MAX_REQUESTS:
            return JSONResponse(status_code=429, content={"detail": "Too many requests"})
    except Exception:
        pass
    response = await call_next(request)
    return response

# Admin config (demo only)
ADMIN_EMAIL = "admin@admin.in"
ADMIN_PASSWORD = "Admin"

# Models
class AdminLogin(BaseModel):
    email: str
    password: str

class ProductIn(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    file_url: str

class ProductOut(ProductIn):
    id: str

class CheckoutIn(BaseModel):
    product_id: str
    buyer_email: str

class OrderOut(BaseModel):
    id: str
    invoice_number: str
    download_url: str

# Helpers

def require_admin(creds: HTTPBasicCredentials = Depends(security)):
    if creds.username.lower() != ADMIN_EMAIL.lower() or creds.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    return True

# Basic email sender (console log). In a real app you'd integrate a provider.
def send_email(to_email: str, subject: str, body: str):
    print(f"\n--- EMAIL ---\nTo: {to_email}\nSubject: {subject}\n\n{body}\n--------------\n")

@app.get("/")
def root():
    return {"message": "Digital products API running"}

@app.get("/schema")
def schema_summary():
    # Expose schemas file so no-code DB viewer can introspect
    try:
        with open("schemas.py", "r") as f:
            return {"schemas": f.read()}
    except Exception:
        return {"schemas": ""}

# Products
@app.post("/admin/product", dependencies=[Depends(require_admin)])
def create_product(payload: ProductIn):
    data = payload.model_dump()
    pid = create_document("product", data)
    return {"id": pid}

@app.get("/products", response_model=List[ProductOut])
def list_products():
    items = get_documents("product")
    out = []
    for it in items:
        out.append(ProductOut(
            id=str(it.get("_id")),
            title=it.get("title"),
            description=it.get("description"),
            price=float(it.get("price", 0)),
            file_url=it.get("file_url"),
        ))
    return out

# Checkout -> creates order, generates invoice, emails customer
@app.post("/checkout", response_model=OrderOut)
def checkout(payload: CheckoutIn):
    # Lookup product
    try:
        prod = db["product"].find_one({"_id": ObjectId(payload.product_id)})
    except Exception:
        prod = None
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    # Generate invoice number
    invoice_seed = f"{payload.buyer_email}-{time.time()}-{payload.product_id}"
    invoice_number = hashlib.sha256(invoice_seed.encode()).hexdigest()[:10].upper()

    # Create secure download token (basic)
    token = hashlib.sha256(f"{invoice_number}-{payload.buyer_email}".encode()).hexdigest()
    download_url = f"/download/{token}"

    order = {
        "product_id": str(prod["_id"]),
        "product_title": prod.get("title"),
        "buyer_email": payload.buyer_email,
        "amount": float(prod.get("price", 0)),
        "currency": "USD",
        "invoice_number": invoice_number,
        "download_url": download_url,
        "created_at": datetime.now(timezone.utc),
    }
    oid = db["order"].insert_one(order).inserted_id

    # Send email (console)
    subject = f"Your invoice #{invoice_number}"
    body = (
        f"Thanks for your purchase!\n\n"
        f"Product: {order['product_title']}\n"
        f"Amount: ${order['amount']} {order['currency']}\n"
        f"Invoice: {invoice_number}\n\n"
        f"Download your file: {download_url}\n"
    )
    send_email(payload.buyer_email, subject, body)

    return OrderOut(id=str(oid), invoice_number=invoice_number, download_url=download_url)

# Very simple token-protected download endpoint (returns file URL reference)
@app.get("/download/{token}")
def download(token: str):
    order = db["order"].find_one({"download_url": f"/download/{token}"})
    if not order:
        raise HTTPException(status_code=404, detail="Invalid token")
    prod = db["product"].find_one({"_id": ObjectId(order["product_id"])})
    if not prod:
        raise HTTPException(status_code=404, detail="Product missing")
    return {"file_url": prod.get("file_url")}

# Admin login test endpoint
@app.get("/admin/whoami")
def whoami(creds: HTTPBasicCredentials = Depends(security)):
    if creds.username.lower() == ADMIN_EMAIL.lower() and creds.password == ADMIN_PASSWORD:
        return {"email": ADMIN_EMAIL}
    raise HTTPException(status_code=401, detail="Invalid admin credentials")

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
