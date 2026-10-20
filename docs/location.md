# Định vị trên điện thoại

## Luồng giao diện

- Bấm Tạo thử thách sẽ tự gọi định vị một lần; không lấy GPS khi chỉ xem bảng tin. Người đăng có thể bỏ vị trí và vẫn đăng bằng đáp án tên địa danh. Vị trí máy có thể khác nơi chụp ảnh trong thư viện, nên giao diện nhắc bỏ tọa độ nếu ảnh chụp nơi khác.
- Chỉ khi mở mục Dự đoán bằng vị trí máy mới tự lấy GPS cho dự đoán. Đóng mục sẽ xóa tọa độ, tránh vô tình gửi GPS khi bình luận bằng chữ.
- Tài khoản người đại diện quản lý vẫn không dùng GPS; backend tiếp tục kiểm tra điều này.
- Chỉ nhận kết quả có sai số không quá 150m. Nếu tìm vị trí bị timeout hoặc không xác định được, thử thêm một lần với kết quả gần đây tối đa 30 giây. Không tự lặp khi bị từ chối quyền. Đóng màn hình hoặc chọn Hủy sẽ bỏ qua kết quả đến trễ.

## Safari báo đã cho phép nhưng vẫn lỗi

Quyền ở website và quyền định vị cấp thiết bị là hai điều cần kiểm tra riêng. Trên iPhone vào Cài đặt → Quyền riêng tư & Bảo mật → Dịch vụ định vị; kiểm tra Trang web Safari và Vị trí chính xác (tên mục có thể thay đổi theo phiên bản iOS). Sau đó kiểm tra quyền Vị trí của đúng tên miền trong Safari, tải lại trang và thử lại. Mở bằng Safari trực tiếp nếu đang dùng trình duyệt nhúng trong ứng dụng khác.

Trang phải ở HTTPS. Dù người dùng đã cho phép, `Permissions-Policy` chặn geolocation cũng gây lỗi PERMISSION_DENIED. Nếu header tại reverse proxy có `geolocation=()`, sửa thành `geolocation=(self)` hoặc bỏ chỉ thị chặn phù hợp với chính sách triển khai. Kiểm tra cả header từ CDN/proxy ngoài ứng dụng; thay JavaScript không vượt được hạn chế do iOS hoặc chính sách bảo mật của trang áp dụng. Không tắt bảo vệ HTTPS để sửa lỗi định vị.

Không thay GPS bị chặn bằng vị trí IP hoặc tọa độ suy đoán. Cần kiểm tra trên iPhone thật để xác nhận quyền thiết bị; kiểm thử trình duyệt có mô phỏng callback chỉ kiểm tra luồng xử lý, không chứng minh máy người dùng đã có quyền.

Tham khảo: [Apple: điều khiển chia sẻ vị trí](https://support.apple.com/guide/iphone/control-the-location-information-you-share-iph3dd5f9be/ios), [lỗi Geolocation](https://developer.mozilla.org/en-US/docs/Web/API/GeolocationPositionError), [Permissions-Policy geolocation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/geolocation).
