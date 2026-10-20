# Kiểm duyệt JinHunt

## Bật trên Ubuntu / Docker

Compose mặc định cài NudeNet 3.4.2 và bật quét cục bộ trên CPU. Ảnh không gửi tới dịch vụ AI bên ngoài. Model 320n đi kèm gói; lần build cần tải thêm các thư viện NumPy, OpenCV và ONNX Runtime. Cấu hình trong `.env`:

```dotenv
MODERATION_REQUIRE_REVIEW=1
AUTO_APPROVE_SCANNED=1
INSTALL_IMAGE_SCANNER=1
IMAGE_SCANNER=nudenet
```

Nếu máy không đủ tài nguyên, có thể đặt `INSTALL_IMAGE_SCANNER=0` và `IMAGE_SCANNER=off`, vẫn giữ `MODERATION_REQUIRE_REVIEW=1`. Khi đó **chưa quét tự động**, mọi ảnh mới tiếp tục chờ người duyệt. Chạy local ngoài Docker cần `pip install -r requirements-moderation.txt` và đặt các biến tương ứng trong môi trường tiến trình (ứng dụng không tự đọc `.env`).

Không đặt `MODERATION_REQUIRE_REVIEW=0` cho bản công khai: đây là chế độ dành cho phát triển/kiểm thử. Model có thể bỏ sót hoặc nhận nhầm; không phải cơ chế xác định tính hợp pháp, độ tuổi hoặc nhận diện danh tính.

## Tạo người có quyền duyệt

Đăng ký một tài khoản người lớn bình thường, hoàn tất điều khoản, rồi chạy trên server:

```bash
sudo docker compose exec api python -m app.manage_staff TEN_DANG_NHAP admin
sudo docker compose exec api python -m app.manage_staff TEN_KIEM_DUYET moderator
```

Lệnh chỉ đổi quyền tài khoản đã tồn tại, không tạo mật khẩu mặc định. Tài khoản phải hoạt động, đủ 18 tuổi, không thuộc luồng phụ huynh. Đăng nhập lại sau khi đổi quyền. Muốn bỏ quyền, chạy cùng lệnh với `user`.

Trong **Hồ sơ → Kiểm duyệt nội dung**, có hàng chờ ảnh, bài và báo cáo. Moderator được duyệt/gỡ ảnh, duyệt/gỡ bài và khóa tài khoản thường. Chỉ admin được mở khóa. Không khóa bản thân hoặc tài khoản có quyền duyệt qua API này; xử lý quyền staff bằng CLI trên server.

## Luồng xử lý

1. Tải ảnh: xóa metadata, đổi kích thước, quét nếu có model. Mặt phát hiện với điểm ít nhất 0,5 được pixel hóa và làm mờ trước khi lưu kết quả; bản trước khi che không được công khai. Không có bộ phát hiện biển số tự động trong phiên bản này.
2. Vùng có nhãn nhạy cảm và điểm ít nhất 0,5 tạo cảnh báo, không tự kết luận vi phạm. Model không phân loại bạo lực, quyền tác giả hoặc ảnh người dưới tuổi. Các nội dung này phải được con người kiểm tra.
3. Với `AUTO_APPROVE_SCANNED=1`, ảnh quét thành công, không bị cảnh báo nhạy cảm và đã che các khuôn mặt phát hiện được sẽ tự được duyệt; bài dùng ảnh đó tự công khai. Không có bộ phát hiện biển số hay kiểm tra bản quyền/bạo lực, vì vậy tự duyệt không chứng minh ảnh tuân thủ mọi quy định. Các ảnh có cảnh báo, quét lỗi hoặc chưa bật bộ quét vẫn chờ người duyệt, không vào feed và không lấy được qua URL công khai. Đặt `AUTO_APPROVE_SCANNED=0` để mọi ảnh mới đều chờ duyệt tay. Người tải và staff có thể xem qua request Authorization. Avatar chờ duyệt không thay avatar công khai hiện có.
4. Staff mở ảnh có chủ đích, kiểm tra và kéo chọn vùng mặt/biển số còn lộ; nhập lý do rồi chọn **Che vùng đã chọn**. Server tạo URL ảnh mới, ngừng phục vụ URL cũ công khai và đưa bài liên quan lại vào hàng chờ. Duyệt ảnh mới rồi duyệt bài.
5. Người dùng bấm **Báo cáo** ở bài hoặc màn hình chi tiết, chọn lý do và mô tả. Báo cáo không công khai danh tính; không tự gỡ bài chỉ vì số lượng báo cáo. Giới hạn 10 báo cáo/giờ/tài khoản, gộp báo cáo đang mở của cùng người cho cùng bài.
6. Gỡ ảnh/bài làm ngừng công khai. Khóa tài khoản thu hồi mọi phiên hiện có, ẩn bài và ảnh của chủ tài khoản. Mở khóa không khôi phục phiên cũ; nội dung đã bị gỡ vẫn bị gỡ.

Mọi quyết định duyệt, gỡ, che và khóa/mở khóa ghi actor, mục tiêu, lý do và thời điểm trong `moderation_audits`. Cấp/thu hồi quyền qua CLI yêu cầu truy cập server. Không có tài khoản admin mặc định hay API công khai tự cấp quyền.

## Dữ liệu cũ và lưu trữ

- Migration giữ bài cũ ở trạng thái đã công khai; chúng chưa được quét lại tự động. Khi có báo cáo, ảnh cũ vào công cụ kiểm tra để staff che/gỡ.
- Gỡ là ngừng hiển thị, không xóa vật lý file/DB. Ảnh gốc đã thay bằng bản che vẫn có thể còn lưu nội bộ cho người có quyền; việc xóa theo yêu cầu và chính sách lưu trữ vẫn cần quy trình vận hành.
- Không tạo thumbnail công khai của ảnh chờ duyệt. Màn hình staff tải ảnh riêng bằng header Authorization, không nhét token vào URL; response ảnh dùng `Cache-Control: no-store`.
- Chưa có hàng đợi nền riêng. Quét ảnh chạy trong thread pool của API; cần theo dõi CPU/RAM, giới hạn tải ở reverse proxy và quy mô người dùng trước khi mở rộng.
- Chính sách được cập nhật phiên bản `2026-10-20.2` để giải thích xử lý ảnh/báo cáo; tài khoản cũ sẽ được yêu cầu xác nhận lại. Vẫn cần hoàn thiện thông tin bên vận hành và quy trình xem xét khiếu nại.

Nguồn model: [NudeNet 3.4.2 và mô tả nhãn](https://pypi.org/project/nudenet/3.4.2/). Kiểm thử thực tế model trên ảnh tổng hợp chỉ xác minh khởi tạo/chạy; không đo độ chính xác trên ảnh người thật hoặc biển số Việt Nam.

Kết quả ảnh lưu trường `decision` để phân biệt tự duyệt, chờ người duyệt và chế độ phát triển. Khi mới bật tự duyệt, cần kiểm tra mẫu các bài công khai và tiếp nhận báo cáo; thay cấu hình không tự quét lại hay tự duyệt ảnh đang tồn trong hàng chờ.
