import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text
from pydantic import BaseModel
from typing import List, Dict, Any, Union
from datetime import datetime
from starlette.responses import JSONResponse

# ====================================================================
# [중요] DB 파일 경로 설정 및 확인
# ====================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "factory.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

if os.path.exists(DB_PATH):
    print(f"✅ DB 연결 성공: {DB_PATH}")
else:
    print(f"❌ DB 파일 없음! 경로를 확인하세요: {DB_PATH}")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ====================================================================
# SQLAlchemy 모델 정의 (DB 테이블명 대문자 적용)
# ====================================================================

class Measurements(Base):
    # ★★★ DB 실제 테이블명: 대문자 "Measurements" ★★★
    __tablename__ = "Measurements"
    
    measure_id = Column(Integer, primary_key=True, index=True) 
    measured_at = Column(String) # 날짜 비교를 위해 String 사용
    inspection_result = Column(String)
    cam1_path = Column(String)
    cam2_path = Column(String)
    product_id = Column(Integer, ForeignKey("Product.product_id")) 
    measured_center = Column(Text)
    measured_contour = Column(Text)
    model_score = Column(Float)
    hole_offset = Column(Float)
    area_size = Column(Float)
    fail_reason = Column(String)

class Product(Base):
    # ★★★ DB 실제 테이블명: 대문자 "Product" ★★★
    __tablename__ = "Product"
    
    product_id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String)
    width = Column(Float)
    length = Column(Float)
    ref_center_point = Column(Float)
    ref_contour = Column(Float)
    # 추가된 컬럼 반영
    template_data = Column(Text)
    limit_fail = Column(Float)
    limit_warn = Column(Float)
    tol_hole = Column(Float)
    tol_shape = Column(Float)

class User(Base):
    # ★★★ DB 실제 테이블명: 대문자 "User" ★★★
    __tablename__ = "User" 
    
    user_id = Column(Integer, primary_key=True, index=True) 
    user_name = Column(String)
    login_id = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(Integer, default=1) 

# ====================================================================
# FastAPI 앱 설정
# ====================================================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    id: str
    pw: str

class LogRequest(BaseModel):
    startDate: str

# ====================================================================
# API 엔드포인트
# ====================================================================

@app.post("/api/login")
async def login(user_login: LoginRequest, db: Session = Depends(get_db)):
    # 1. 비상용 하드코딩 계정
    if user_login.id == "1234" and user_login.pw == "1234":
        return JSONResponse(status_code=200, content={"message": "Login successful (Admin)"})

    # 2. DB 로그인 (평문 비교)
    user = db.query(User).filter(User.login_id == user_login.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user_login.pw != user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return JSONResponse(status_code=200, content={"message": "Login successful"})

@app.post("/api/logs")
async def get_logs(req: LogRequest, db: Session = Depends(get_db)):
    try:
        print(f"Requested Log Date: {req.startDate}") 

        # 쿼리 구성
        query = db.query(
            Measurements.measure_id,
            Measurements.measured_at,
            Measurements.inspection_result,
            Measurements.product_id 
        )

        # 날짜 필터링 ('ALL'이 아닐 경우 LIKE 사용)
        if req.startDate.upper() != 'ALL':
            query = query.filter(Measurements.measured_at.like(f"{req.startDate}%"))
            
        logs = query.order_by(Measurements.measured_at.desc()).all()
        
        print(f"Fetched {len(logs)} logs.") 
        
        results = []
        for mid, timestamp, result, product_id in logs:
            product_name = f"Product {product_id}" if product_id else "Unknown"
            
            results.append({
                "mid": mid,
                "timestamp": str(timestamp), 
                "result": result,
                "product_name": product_name 
            })
        
        return results
        
    except Exception as e:
        print(f"Log Error: {e}")
        raise HTTPException(status_code=500, detail=f"Log query failed: {e}")

# 시스템 제어 더미 API
@app.post("/api/start")
def start_system(data: Dict[str, Any]):
    return JSONResponse(status_code=200, content={"message": "System started"})

@app.post("/api/restart")
def restart_system(data: Dict[str, Any]):
    return JSONResponse(status_code=200, content={"message": "System restarted"})

@app.post("/api/stop")
def stop_system(data: Dict[str, Any]):
    return JSONResponse(status_code=200, content={"message": "System stopped"})