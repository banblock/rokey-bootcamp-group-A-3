# NoSQL/db_manager.py
import datetime
import random
from pymongo import MongoClient

class BookDatabaseManager:
    def __init__(self, db_url="mongodb://localhost:27017/", db_name="book_binder_db"):
        """MongoDB 연결 초기화"""
        try:
            self.client = MongoClient(db_url, serverSelectionTimeoutMS=2000)
            self.db = self.client[db_name]
            self.books = self.db["books"]
            print(f"✔ [DB] '{db_name}' 데이터베이스에 연결되었습니다.")
        except Exception as e:
            print(f"❌ [DB] 연결 실패: {e}")
            self.books = None

    def insert_new_book(self, title, width, length, thickness, weight):
        """
        [기능 1: 새 책 정보 저장]
        시스템 컨트롤단이 던져준 책의 제목과 물리적 스펙을 기반으로 
        고유 QR 키(book_id)와 목표 분류 위치를 자동 매핑하여 MongoDB에 적재합니다.
        """
        if self.books is None: return None

        # QR 코드로 인쇄 및 인식될 고유 키값 생성
        book_id = f"BOOK_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
        target_location = random.randint(0,3)

        book_document = {
            "book_id": book_id,            # QR 키값
            "title": title,                # 책 제목
            "dimensions": {                # 크기
                "width": float(width),
                "length": float(length),
                "thickness": float(thickness)
            },
            "weight": int(weight),         # 무게
            "target_location": target_location, # 목표 매핑 위치
            "registered_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            self.books.insert_one(book_document)
            print(f"📁 [DB] 신규 도서 적재 완료 (QR Key: {book_id})")
            return book_document  # 생성된 정보를 리턴하여 컨트롤단이 인쇄 등으로 활용할 수 있게 함
        except Exception as e:
            print(f"❌ [DB] 저장 오류: {e}")
            return None

    def get_book_by_qr(self, qr_code):
        """
        [기능 2: QR 키에 따른 책 정보 조회 및 전송]
        카메라가 책의 QR 코드를 인식하여 qr_code(문자열)를 넘겨주면, 
        DB에서 해당 책 정보(제목, 크기, 무게, 목표 위치) 딕셔너리를 딱 하나 찾아 반환합니다.
        """
        if self.books is None: return None
        
        # MongoDB 내부 식별자인 _id 필드는 제외하고 약속된 데이터 형식 구조만 리턴
        return self.books.find_one({"book_id": qr_code}, {"_id": 0})