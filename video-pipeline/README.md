# Nava video pipeline — HeyGen + footage nhà máy

Luồng 1 video (30–60s, 9:16, tiếng Anh):

1. Claude chọn chủ đề từ trend đa nền tảng và viết `plans/<ID>.json`: kịch bản EN + VI, đoạn nào chèn cảnh công đoạn nào, caption, hashtag.
2. `run.py` gửi kịch bản lên HeyGen (avatar **San**, voice **San Nguyễn Van**, 1080×1920) rồi tải video về.
3. Canh thời gian từng từ, lấy clip **chưa bị khoá** trong `NAVA — KHO FOOTAGE/1_KHO DÙNG ĐƯỢC/<công đoạn>`. Mỗi cảnh cắt dài tối đa 3,6s, tắt tiếng gốc.
4. Dựng: avatar toàn màn hình, xen cảnh xưởng, punch-in, phụ đề nảy từng từ (từ khoá màu vàng), hook trên đầu 3s, nhạc nền tự giảm khi có giọng. Âm lượng chuẩn -14 LUFS.
5. Đưa thành phẩm và kịch bản lên `4_THÀNH PHẨM HEYGEN (chờ Liam duyệt)/<ID>/`.
6. Clip đã dùng được ghi vào sheet **SỔ FOOTAGE ĐÃ DÙNG** và chuyển sang `3_ĐANG KHOÁ…/Mở lại <ngày>`.
7. `release.py` chạy hằng ngày theo lịch, trả các clip hết hạn khoá về đúng thư mục công đoạn.

Thời gian khoá clip đặt ở `config.json` → `cooldown_days` (mặc định 60).

## Cấu hình một lần trong môi trường

**Network → Allowed domains:**
- `api.heygen.com`, `upload.heygen.com`
- `*.heygen.ai`, `*.heygen.com` (để tải video đã render)
- `huggingface.co`, `*.hf.co` (không bắt buộc, giúp phụ đề khớp tiếng chính xác hơn)

**Secrets / biến môi trường:**

| Biến | Lấy ở đâu |
|---|---|
| `HEYGEN_API_KEY` | HeyGen → Settings → API |
| `GOOGLE_OAUTH_CLIENT_ID` | Google Cloud Console → APIs & Services → Credentials → OAuth client (Desktop) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | như trên |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | developers.google.com/oauthplayground: bật "Use your own OAuth credentials", scope `https://www.googleapis.com/auth/drive`, đăng nhập bằng tài khoản sở hữu Drive, Exchange để lấy refresh token |

## Lệnh

```bash
pip install -r requirements.txt
python run.py plans/NH-20261025-HG1.json                    # chạy đầy đủ
python run.py plans/X.json --avatar heygen.mp4             # đã có video HeyGen, bỏ qua bước render
python run.py plans/X.json --local-broll DIR --no-drive    # dựng thử offline
python release.py                                          # mở khoá clip hết hạn
```

## Quy ước tải footage lên

- Thả clip thô vào đúng thư mục công đoạn `00`–`19`. Không rõ công đoạn thì để vào `00 INBOX`, Claude sẽ xem rồi xếp.
- Nên quay dọc 9:16 hoặc ngang 4K (máy tự crop), mỗi clip từ 4s trở lên, cận cảnh tay thợ. Không cần tiếng.
- Nhạc nền: tải nhạc miễn phí bản quyền (YouTube Audio Library, Pixabay Music) vào `5_NHẠC NỀN/A–D` theo mood. Thư mục trống thì máy tự tổng hợp một nền nhạc nhẹ.
