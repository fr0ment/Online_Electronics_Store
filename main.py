from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import logging
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from database import SessionLocal, engine, Base
import models
import schemas
import crud
from fastapi.security import OAuth2PasswordRequestForm

# Настройка логирования
logging.basicConfig(filename='app.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()

# Настройка JWT
SECRET_KEY = "713ffca054a07569fb29a73a0cec5f661933d44f5c4c64020508f96796e98624"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Настройка хеширования
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# OAuth2 схема
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

# Функция создания токена
def create_access_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Зависимости
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        print(f"Received token: {token}")  
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = crud.get_user_by_email(db, email)
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError as e:
        print(f"JWT error: {str(e)}")  
        raise HTTPException(status_code=401, detail="Invalid token")

# Аутентификация
@app.post("/api/auth/login", tags=["Users"])
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    logging.info(f"Получен запрос на вход с данными: username={form_data.username}, password={form_data.password}")
    db_user = crud.get_user_by_email(db, form_data.username)
    if not db_user or not pwd_context.verify(form_data.password, db_user.hashed_password):
        logging.warning(f"Неудачная попытка входа для {form_data.username}")
        raise HTTPException(status_code=401, detail="Неверные учетные данные")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": db_user.email}, expires_delta=access_token_expires)
    logging.info(f"Пользователь {db_user.email} успешно вошел")
    return {"access_token": access_token, "token_type": "bearer"}

# Эндпоинты для товаров
@app.get("/api/products", response_model=List[schemas.Product], tags=["Products"])
async def get_products(
    page: int = 1,
    limit: int = 10,
    category: Optional[str] = None,
    minPrice: Optional[float] = None,
    maxPrice: Optional[float] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    db: Session = Depends(get_db)
):
    if page < 1 or limit < 1 or limit > 100:
        logging.warning(f"Invalid pagination params: page={page}, limit={limit}")
        raise HTTPException(status_code=400, detail="Invalid pagination parameters")
    
    products = crud.get_products(db, page=page, limit=limit, category=category, min_price=minPrice, max_price=maxPrice, sort_by=sort_by, sort_order=sort_order)
    logging.info(f"Fetched products: page={page}, limit={limit}, category={category}, minPrice={minPrice}, maxPrice={maxPrice}, sort_by={sort_by}, sort_order={sort_order}")
    return products

@app.get("/api/products/{id}", response_model=schemas.Product, tags=["Products"])
async def get_product(id: int, db: Session = Depends(get_db)):
    product = crud.get_product(db, id)
    if product is None:
        logging.warning(f"Product {id} not found")
        raise HTTPException(status_code=404, detail="Product not found")
    logging.info(f"Fetched product {id}")
    return product

@app.post("/api/products", response_model=schemas.Product, tags=["Products"])
async def create_product(
    product: schemas.ProductCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ["manager", "admin"]:
        logging.warning(f"Unauthorized product creation attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized")
    
    new_product = crud.create_product(db, product)
    logging.info(f"Product {new_product.id} created by {current_user.email}")
    return new_product

@app.put("/api/products/{id}", response_model=schemas.Product, tags=["Products"])
async def update_product(
    id: int,
    product: schemas.ProductCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ["manager", "admin"]:
        logging.warning(f"Unauthorized product update attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized")
    
    updated_product = crud.update_product(db, id, product)
    if updated_product is None:
        logging.warning(f"Product {id} not found for update")
        raise HTTPException(status_code=404, detail="Product not found")
    logging.info(f"Product {id} updated by {current_user.email}")
    return updated_product

@app.delete("/api/products/{id}", tags=["Products"])
async def delete_product(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ["manager", "admin"]:
        logging.warning(f"Unauthorized product deletion attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not crud.delete_product(db, id):
        logging.warning(f"Product {id} not found for deletion")
        raise HTTPException(status_code=404, detail="Product not found")
    logging.info(f"Product {id} deleted by {current_user.email}")
    return {"message": "Product deleted"}

# Эндпоинты для заказов
@app.get("/api/orders", response_model=List[schemas.Order], tags=["Orders"])
async def get_orders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role in ["admin", "manager"]:
        orders = crud.get_all_orders(db)
    else:
        orders = crud.get_user_orders(db, current_user.id)
    logging.info(f"Fetched orders for {current_user.email}")
    return orders

@app.get("/api/orders/{id}", response_model=schemas.Order, tags=["Orders"])
async def get_order(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    order = crud.get_order(db, id)
    if order is None:
        logging.warning(f"Order {id} not found")
        raise HTTPException(status_code=404, detail="Order not found")
    if current_user.role not in ["admin", "manager"] and order.user_id != current_user.id:
        logging.warning(f"Unauthorized order access attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized")
    logging.info(f"Fetched order {id} for {current_user.email}")
    return order

@app.post("/api/orders", response_model=schemas.Order, tags=["Orders"])
async def create_order(
    order: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "customer":
        logging.warning(f"Unauthorized order creation attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized")
    
    new_order = crud.create_order(db, order, current_user.id)
    logging.info(f"Order {new_order.id} created by {current_user.email}")
    return new_order

@app.put("/api/orders/{id}", response_model=schemas.Order, tags=["Orders"])
async def update_order(
    id: int,
    order: schemas.OrderUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ["manager", "admin"]:
        logging.warning(f"Unauthorized order update attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized")
    
    updated_order = crud.update_order(db, id, order)
    if updated_order is None:
        logging.warning(f"Order {id} not found for update")
        raise HTTPException(status_code=404, detail="Order not found")
    logging.info(f"Order {id} updated by {current_user.email}")
    return updated_order

@app.delete("/api/orders/{id}", tags=["Orders"])
async def delete_order(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "admin":
        logging.warning(f"Unauthorized order deletion attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not crud.delete_order(db, id):
        logging.warning(f"Order {id} not found for deletion")
        raise HTTPException(status_code=404, detail="Order not found")
    logging.info(f"Order {id} deleted by {current_user.email}")
    return {"message": "Order deleted"}

# Эндпоинты для отзывов
@app.get("/api/reviews", response_model=List[schemas.Review], tags=["Reviews"])
async def get_reviews(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role == "admin":
        reviews = crud.get_all_reviews(db)
    else:
        reviews = crud.get_approved_reviews(db)
    logging.info(f"Fetched reviews for {current_user.email}")
    return reviews

@app.get("/api/reviews/{id}", response_model=schemas.Review, tags=["Reviews"])
async def get_review(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    review = crud.get_review(db, id)
    if review is None:
        logging.warning(f"Review {id} not found")
        raise HTTPException(status_code=404, detail="Review not found")
    if current_user.role not in ["admin"] and not review.is_approved:
        logging.warning(f"Unauthorized review access attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Review not approved")
    logging.info(f"Fetched review {id} for {current_user.email}")
    return review

@app.post("/api/reviews", response_model=schemas.Review, tags=["Reviews"])
async def create_review(
    review: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "customer":
        logging.warning(f"Unauthorized review creation attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized")
    
    new_review = crud.create_review(db, review, current_user.id)
    logging.info(f"Review {new_review.id} created by {current_user.email}")
    return new_review

@app.put("/api/reviews/{id}", response_model=schemas.Review, tags=["Reviews"])
async def update_review(
    id: int,
    review: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    db_review = crud.get_review(db, id)
    if db_review is None:
        logging.warning(f"Review {id} not found for update")
        raise HTTPException(status_code=404, detail="Review not found")
    if current_user.role not in ["admin"] and db_review.user_id != current_user.id:
        logging.warning(f"Unauthorized review update attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized")
    
    updated_review = crud.update_review(db, id, review)
    logging.info(f"Review {id} updated by {current_user.email}")
    return updated_review

@app.delete("/api/reviews/{id}", tags=["Reviews"])
async def delete_review(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    db_review = crud.get_review(db, id)
    if db_review is None:
        logging.warning(f"Review {id} not found for deletion")
        raise HTTPException(status_code=404, detail="Review not found")
    if current_user.role not in ["admin"] and db_review.user_id != current_user.id:
        logging.warning(f"Unauthorized review deletion attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized")
    
    crud.delete_review(db, id)
    logging.info(f"Review {id} deleted by {current_user.email}")
    return {"message": "Review deleted"}

@app.post("/api/reviews/{id}/moderate", tags=["Reviews"])
async def moderate_review(
    id: int,
    moderation: schemas.ReviewModeration,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "admin":
        logging.warning(f"Unauthorized review moderation attempt by {current_user.email}")
        raise HTTPException(status_code=403, detail="Not authorized")
    
    review = crud.moderate_review(db, id, moderation.is_approved)
    if review is None:
        logging.warning(f"Review {id} not found for moderation")
        raise HTTPException(status_code=404, detail="Review not found")
    logging.info(f"Review {id} moderated by {current_user.email}: approved={moderation.is_approved}")
    return review

# Инициализация базы данных
Base.metadata.create_all(bind=engine)

# Посев данных
@app.on_event("startup")
async def startup_event():
    db = SessionLocal()
    try:
        crud.seed_database(db)
        logging.info("Database seeded successfully")
    finally:
        db.close()