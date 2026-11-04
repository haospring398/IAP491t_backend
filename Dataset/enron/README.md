# Dataset/enron/

Bỏ dữ liệu Enron (email hợp lệ, nhãn 0) vào đây.

`load_data.py` đọc **đệ quy** toàn bộ file trong thư mục này (và các thư
mục con), mỗi file = 1 email thô (raw RFC-822), không cần đuôi file —
đúng định dạng maildir gốc của Enron (giống file mẫu bạn đã gửi: có
Message-ID, Date, From, To, Subject...).

Ví dụ cấu trúc hợp lệ:

```
Dataset/enron/
├── maildir/
│   └── arora-h/
│       └── inbox/
│           ├── 1.
│           ├── 2.
│           └── ...
```

(Cây thư mục con bên trong sâu bao nhiêu cấp cũng được, `load_data.py`
tự `os.walk()` để tìm hết.)
