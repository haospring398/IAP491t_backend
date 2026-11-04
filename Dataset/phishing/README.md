# Dataset/phishing/

Bỏ dữ liệu Nazario (email phishing, nhãn 1) vào đây.

`load_data.py` đọc mọi file `.mbox` (hoặc `.txt` dạng mbox) trong thư mục
này — đúng định dạng Nazario corpus tải từ
https://monkey.org/~jose/phishing/ (vd `phishing3.mbox`,
`phishing-2020_2.mbox`, `private-phishing4.mbox`...).

Ví dụ cấu trúc hợp lệ:

```
Dataset/phishing/
├── phishing-2015.mbox
├── phishing-2020_2.mbox
├── phishing3.mbox
└── ...
```

Có thể để nhiều file `.mbox` cùng lúc — `load_data_phishing()` sẽ gộp hết
lại thành 1 dataset duy nhất.
