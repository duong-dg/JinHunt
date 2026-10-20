# Thử cấp và khung avatar trên server Ubuntu

Chạy trong thư mục JinHunt có docker-compose.yml. Công cụ không có API công khai, chỉ người có quyền chạy Docker trên server sử dụng được. Mật khẩu nhập ẩn trong terminal, không truyền trong dòng lệnh hay commit vào Git.

## Tạo tài khoản ngay trước mốc cấp 5

```bash
sudo docker compose exec api python -m app.test_account create --username jhtest_demo --level 5 --before-level
```

Nhập mật khẩu hai lần. Tài khoản được tạo với 999 XP (cấp 4). Đăng nhập tại https://jinhunt.io.vn bằng tên jhtest_demo và mật khẩu vừa nhập. Đọc và đồng ý điều khoản, nhập ngày sinh của người thực sự dùng tài khoản qua giao diện. Không có consent giả, không tự xác minh email và không cấp quyền quản trị. Luồng người đại diện vẫn áp dụng nếu người dùng khai dưới 18 tuổi.

Bấm Điểm danh lần đầu trong ngày: +5 XP, đạt cấp 5, khung Đồng và thông báo chúc mừng. Nếu đã điểm danh, dùng tài khoản khác đăng bài đã duyệt rồi tương tác để vượt mốc. Tương tác nhiều lần với bài đã nhận điểm không được cộng thêm.

## Đổi cấp tài khoản test đã tạo

```bash
sudo docker compose exec api python -m app.test_account set-level --username jhtest_demo --level 10
sudo docker compose exec api python -m app.test_account set-level --username jhtest_demo --level 20
sudo docker compose exec api python -m app.test_account set-level --username jhtest_demo --level 30
sudo docker compose exec api python -m app.test_account set-level --username jhtest_demo --level 50
sudo docker compose exec api python -m app.test_account set-level --username jhtest_demo --level 75
sudo docker compose exec api python -m app.test_account set-level --username jhtest_demo --level 100
sudo docker compose exec api python -m app.test_account set-level --username jhtest_demo --level 150
```

Cấp 5 Đồng, 10 Bạc, 20 Vàng, 30 Bạch kim, 50 Kim cương, 75 Hồng ngọc, 100 Hoàng gia, 150 Huyền thoại. Lệnh test hỗ trợ cấp 1–200. Cấp 1–4 không có khung. Tải lại trang để nhận dữ liệu mới. Muốn xem thông báo tăng cấp, mở tài khoản khi đang cấp thấp trước, sau đó gán cấp cao và tải lại. Lần đăng nhập đầu tiên chỉ ghi nhận cấp hiện tại, không hiện chúc mừng giả.

Để thử lên cấp bằng chơi thật thay vì gán thẳng, thêm --before-level vào set-level rồi kiếm thêm điểm. Công cụ không xóa lịch sử nhận thưởng; điểm danh vẫn một lần/ngày, thưởng tương tác vẫn một lần/bài.

Tên test bắt đầu bằng jhtest_. Lệnh create từ chối tên đã tồn tại; set-level chỉ cho tài khoản có cờ is_test do công cụ tạo. XP được đặt thành mốc cấp chỉ định (có thể tăng hoặc giảm), không đổi mật khẩu, quyền hay trạng thái duyệt. Tài khoản test không xuất hiện trong bảng xếp hạng; bài test vẫn là nội dung thật và cần kiểm duyệt bình thường.
