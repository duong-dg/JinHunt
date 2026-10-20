# Điểm JinHunt

- Đoán đúng: người đầu 50 XP, thứ hai 25, thứ ba 10, các người sau 5. Thứ tự là thứ tự máy chủ ghi nhận thành công, dùng chung cho dự đoán chữ và GPS.
- Bình luận: 1 XP/người/bài, chỉ lần đầu; bình luận đoán đúng có thể nhận cả điểm giải và điểm bình luận.
- Thả tim: 1 XP/người/bài; bỏ tim rồi thả lại không cộng thêm.
- Không tính điểm bình luận/thả tim trên bài của chính mình.
- Chủ bài chia sẻ bằng nút Chia sẻ nhận 10 XP/bài khi một người khác mở link có mã chia sẻ rồi thả tim, bình luận hoặc giải đúng. Chỉ bấm Chia sẻ hay mở link không có điểm. Máy chủ không xác minh được việc gửi qua mạng xã hội; chỉ xác nhận tương tác gắn với link. Liên kết phải là bài đã công khai.
- Ghi nhớ nguồn chia sẻ trong sessionStorage trong 24 giờ; hoạt động trong cùng tab/trình duyệt, không theo dõi xuyên thiết bị. Xóa dữ liệu hoặc đổi tab có thể mất nguồn.
- Sổ điểm lưu một lần theo người/bài/loại, độc lập với bản ghi tim và bình luận. Điểm cũ được giữ, không tính lại lịch sử. Những lượt giải cũ vẫn được tính khi xác định thứ hạng tiếp theo.
- Các bảng point_awards và case_shares được tạo tự động khi khởi động bản mới.


## Cấp và hoạt động hằng ngày

- Cấp 1 lên 2 cần 200 XP. Mỗi cấp tiếp theo cần thêm 15% so với cấp trước, làm tròn lên đến XP nguyên: 200 → 230 → 265 → 305 → 351… Tổng XP đạt cấp là tổng chi phí các cấp trước, không nhân trực tiếp tổng XP với 15%.
- Viền avatar: cấp 1–4 không viền, 5–9 Đồng, 10–19 Bạc, 20–29 Vàng, 30–49 Bạch kim, 50–74 Kim cương, 75–99 Hồng ngọc, 100–149 Hoàng gia, từ 150 Huyền thoại.
- Tổng XP cũ giữ nguyên; cấp được tính lại theo công thức mới, vì vậy tài khoản cũ có thể hiển thị cấp thấp hơn trước. Bảng xếp hạng vẫn sắp theo tổng XP.
- Điểm danh: bấm nhận 5 XP một lần/ngày. Không tự nhận khi chỉ mở trang.
- Nhiệm vụ: giải đúng một bài chưa giải để tự nhận thêm 10 XP một lần/ngày. Không nhận lại bằng cách trả lời bài đã giải từ ngày trước. Cộng cùng với điểm thứ hạng và điểm bình luận nếu có.
- Ngày tính theo UTC+7 (giờ Việt Nam), máy chủ quyết định; không phụ thuộc đồng hồ điện thoại. Mốc ngày mới 00:00. Không có thưởng chuỗi ngày và không trừ điểm nếu bỏ lỡ.
- daily_rewards có ràng buộc duy nhất người/ngày/loại để tránh nhận nhiều lần hoặc qua nhiều thiết bị. Bảng được tạo tự động khi khởi động.

- Hạng cao: Hồng ngọc có đá ruby đỏ; Hoàng gia tím vàng và vương miện; Huyền thoại vàng trắng với biểu tượng phượng hoàng. Tên và khung avatar theo màu hạng trên toàn bộ giao diện.
- Giữ đường XP tăng 15% mỗi cấp; không tự nâng cấp tài khoản cũ. users.total_xp dùng BIGINT trên PostgreSQL để lưu các mốc cao mà không tràn số nguyên 32-bit. Migration tự nâng kiểu, không thay đổi số điểm.
- Lệnh test cho phép cấp 1–200; tổng XP của mốc 200 vẫn trong giới hạn số nguyên chính xác của JavaScript. Hiển thị XP lớn được rút gọn theo định dạng tiếng Việt; API vẫn trả tổng số nguyên đầy đủ.
