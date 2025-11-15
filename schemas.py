"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field("digital", description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")
    file_url: str = Field(..., description="Secure URL to the digital file")

class Order(BaseModel):
    """
    Orders collection schema
    Collection name: "order" (lowercase of class name)
    """
    product_id: str = Field(..., description="ID of the purchased product")
    product_title: str = Field(..., description="Title of product at time of purchase")
    buyer_email: str = Field(..., description="Customer email to deliver invoice")
    amount: float = Field(..., ge=0, description="Total amount charged")
    currency: str = Field("USD", description="Currency code")
    invoice_number: str = Field(..., description="Unique invoice number")
    download_url: str = Field(..., description="URL the customer can use to download their purchase")
