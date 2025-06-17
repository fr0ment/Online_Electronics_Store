from sqlalchemy.orm import Session
from passlib.context import CryptContext
import models
import schemas
from typing import List, Optional

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_products(db: Session, page: int, limit: int, category: Optional[str], min_price: Optional[float], max_price: Optional[float], sort_by: Optional[str], sort_order: Optional[str], in_stock: Optional[bool] = None):
    query = db.query(models.Product)
    if category:
        valid_categories = [cat[0] for cat in db.query(models.Product.category).distinct().all()]
        if category not in valid_categories:
            raise ValueError("Invalid category")
        query = query.filter(models.Product.category == category)
    if min_price is not None:
        query = query.filter(models.Product.price >= min_price)
    if max_price is not None:
        query = query.filter(models.Product.price <= max_price)
    if in_stock is not None and in_stock:
        query = query.filter(models.Product.stock > 0)
    if sort_by in ["name", "price"] and sort_order in ["asc", "desc"]:
        order_column = getattr(models.Product, sort_by)
        query = query.order_by(order_column.asc() if sort_order == "asc" else order_column.desc())
    return query.offset((page - 1) * limit).limit(limit).all()

def get_product(db: Session, product_id: int):
    return db.query(models.Product).filter(models.Product.id == product_id).first()

def create_product(db: Session, product: schemas.ProductCreate):
    db_product = models.Product(**product.dict())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

def update_product(db: Session, product_id: int, product: schemas.ProductCreate):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if db_product:
        for key, value in product.dict().items():
            setattr(db_product, key, value)
        db.commit()
        db.refresh(db_product)
    return db_product

def delete_product(db: Session, product_id: int):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if db_product:
        db.delete(db_product)
        db.commit()
        return True
    return False

def get_all_orders(db: Session):
    return db.query(models.Order).all()

def get_user_orders(db: Session, user_id: int):
    return db.query(models.Order).filter(models.Order.user_id == user_id).all()

def get_order(db: Session, order_id: int):
    return db.query(models.Order).filter(models.Order.id == order_id).first()

def create_order(db: Session, order: schemas.OrderCreate, user_id: int):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise ValueError("User not found")
    
    db_order = models.Order(**order.dict(), user_id=user_id)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    db_order.total = 0.0
    db.commit()
    db.refresh(db_order)
    return db_order

def create_order_item(db: Session, order_id: int, product_id: int, quantity: int):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product or db_product.stock < quantity:
        raise ValueError("Insufficient stock or product not found")
    
    db_order_item = models.OrderItem(order_id=order_id, product_id=product_id, quantity=quantity)
    db.add(db_order_item)
    db_product.stock -= quantity
    db.commit()
    db.refresh(db_order_item)

    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if db_order:
        total = sum(item.quantity * db.query(models.Product).filter(models.Product.id == item.product_id).first().price 
                   for item in get_order_items(db, order_id))
        db_order.total = total
        db.commit()
        db.refresh(db_order)
    
    return db_order_item

def get_order_items(db: Session, order_id: int):
    return db.query(models.OrderItem).filter(models.OrderItem.order_id == order_id).all()


def update_order(db: Session, order_id: int, order: schemas.OrderUpdate):
    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if db_order:
        for key, value in order.dict(exclude_unset=True).items():
            setattr(db_order, key, value)

        total = sum(item.quantity * db.query(models.Product).filter(models.Product.id == item.product_id).first().price 
                   for item in get_order_items(db, order_id))
        db_order.total = total
        db.commit()
        db.refresh(db_order)
    return db_order

def delete_order(db: Session, order_id: int):
    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if db_order:
        db.delete(db_order)
        db.commit()
        return True
    return False

def get_all_reviews(db: Session):
    return db.query(models.Review).all()

def get_approved_reviews(db: Session):
    return db.query(models.Review).filter(models.Review.is_approved == True).all()

def get_review(db: Session, review_id: int):
    return db.query(models.Review).filter(models.Review.id == review_id).first()

def update_product_rating(db: Session, product_id: int):
    reviews = db.query(models.Review).filter(models.Review.product_id == product_id, 
                                           models.Review.is_approved == True).all()
    if reviews:
        avg_rating = sum(review.rating for review in reviews) / len(reviews)
        product = db.query(models.Product).filter(models.Product.id == product_id).first()
        if product:
            product.average_rating = avg_rating
            db.commit()

def create_review(db: Session, review: schemas.ReviewCreate, user_id: int):
    db_review = models.Review(**review.dict(), user_id=user_id)
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    update_product_rating(db, review.product_id)
    return db_review

def update_review(db: Session, review_id: int, review: schemas.ReviewCreate):
    db_review = db.query(models.Review).filter(models.Review.id == review_id).first()
    if db_review:
        for key, value in review.dict().items():
            setattr(db_review, key, value)
        db_review.is_approved = False
        db.commit()
        db.refresh(db_review)
    return db_review

def delete_review(db: Session, review_id: int):
    db_review = db.query(models.Review).filter(models.Review.id == review_id).first()
    if db_review:
        db.delete(db_review)
        db.commit()
        return True
    return False

def moderate_review(db: Session, review_id: int, is_approved: bool):
    db_review = db.query(models.Review).filter(models.Review.id == review_id).first()
    if db_review:
        db_review.is_approved = is_approved
        db.commit()
        db.refresh(db_review)
        update_product_rating(db, db_review.product_id)
    return db_review

def seed_database(db: Session):
    if db.query(models.User).count() == 0:
        users = [
            models.User(email="buyer@example.com", hashed_password=pwd_context.hash("Buyer123!"), role="customer"),
            models.User(email="manager@example.com", hashed_password=pwd_context.hash("Manager123!"), role="manager"),
            models.User(email="admin@example.com", hashed_password=pwd_context.hash("Admin123!"), role="admin"),
        ]
        db.add_all(users)
        
        products = [
            models.Product(name="Смартфон", price=15000.0, category="smartphones", description="Хороший смартфон", stock=10),
            models.Product(name="Ноутбук", price=50000.0, category="laptops", description="Мощный ноутбук", stock=5),
        ]
        db.add_all(products)
        db.commit()
        
        orders = [
            models.Order(user_id=1, status="pending", total=0.0),
        ]
        db.add_all(orders)
        db.commit()
        
        order_item = models.OrderItem(order_id=1, product_id=1, quantity=1)
        db.add(order_item)
        db.commit()
        
        reviews = [
            models.Review(product_id=1, user_id=1, rating=4, text="Хороший телефон", is_approved=True),
        ]
        db.add_all(reviews)
        db.commit()