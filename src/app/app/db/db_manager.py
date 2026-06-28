# app/db/db_manager.py
import datetime
from pymongo import MongoClient, ASCENDING, DESCENDING


class BookDatabaseManager:
    def __init__(self, db_url="mongodb://localhost:27017/", db_name="book_binder_db"):
        """MongoDB 연결 초기화"""
        self.client = None
        self.db = None
        self.books = None

        try:
            self.client = MongoClient(db_url, serverSelectionTimeoutMS=2000)
            self.client.admin.command("ping")

            self.db = self.client[db_name]
            self.books = self.db["books"]

            # 숫자 기반 ID/QR 중복 방지
            self.books.create_index([("book_id", ASCENDING)], unique=True)
            self.books.create_index([("qr_code", ASCENDING)], unique=True, sparse=True)
            self.books.create_index([("target_location", ASCENDING)])

            print(f"✔ [DB] '{db_name}' 데이터베이스에 연결되었습니다.")

        except Exception as e:
            print(f"❌ [DB] 연결 실패: {e}")
            self.client = None
            self.db = None
            self.books = None

    def _generate_next_book_id(self):
        """
        숫자형 book_id를 1부터 자동 증가시킨다.
        기존 문자열 book_id 문서는 무시한다.
        """
        if self.books is None:
            return 1

        last_doc = self.books.find_one(
            {"book_id": {"$type": "number"}},
            {"book_id": 1, "_id": 0},
            sort=[("book_id", DESCENDING)]
        )

        if not last_doc:
            return 1

        return int(last_doc.get("book_id", 0)) + 1

    def insert_new_book(self, title, width, length, thickness, section):
        """
        새 책 정보 저장.

        저장 형식:
            book_id: int
            qr_code: int
            target_location: int
            dimensions.width/length/thickness: float, mm 단위

        UI 쪽 호출 형식:
            insert_new_book(title, width, length, thickness, section)
        """
        if self.books is None:
            return None

        try:
            book_id = self._generate_next_book_id()
            target_location = int(section)

            book_document = {
                "book_id": int(book_id),
                "qr_code": int(book_id),
                "title": str(title),
                "dimensions": {
                    "width": float(width),
                    "length": float(length),
                    "thickness": float(thickness),
                },
                "target_location": int(target_location),
                "registered_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            self.books.insert_one(book_document)

            # UI/Controller에서 _id 직렬화 문제 없도록 제거해서 반환
            book_document.pop("_id", None)

            print(
                f"📁 [DB] 신규 도서 적재 완료 "
                f"(book_id={book_id}, qr_code={book_id}, target_location={target_location})"
            )
            return book_document

        except Exception as e:
            print(f"❌ [DB] 저장 오류: {e}")
            return None

    def get_book_by_qr(self, qr_code):
        """
        QR 값으로 책 정보 조회.
        Vision/QR에서 문자열 '1'로 들어와도 숫자 1로 변환해서 조회한다.
        """
        if self.books is None:
            return None

        try:
            qr_value = int(str(qr_code).strip())
        except (TypeError, ValueError):
            print(f"❌ [DB] QR 값이 숫자가 아닙니다: {qr_code}")
            return None

        return self.books.find_one(
            {
                "$or": [
                    {"qr_code": qr_value},
                    {"book_id": qr_value},
                ]
            },
            {"_id": 0}
        )

    # ui_node.py 호환용 alias들
    def find_book_by_qr(self, qr_code):
        return self.get_book_by_qr(qr_code)

    def find_book_by_qr_code(self, qr_code):
        return self.get_book_by_qr(qr_code)

    def get_book_by_qr_code(self, qr_code):
        return self.get_book_by_qr(qr_code)

    def find_book_by_id(self, book_id):
        return self.get_book_by_qr(book_id)

    def get_book_by_id(self, book_id):
        return self.get_book_by_qr(book_id)
