# JinHunt — hồ sơ rà soát trước phát hành

Đây là bản triển khai để chủ dự án và người tư vấn pháp lý xem xét, **không phải xác nhận đã đáp ứng toàn bộ pháp luật**. Phạm vi đang soạn theo Việt Nam. Không tự suy ra giấy phép, đăng ký, nghĩa vụ xác thực hay nghĩa vụ dữ liệu đã hoàn thành từ việc có trang điều khoản.

## Đã có trong code

- `/terms`, `/privacy`, `/copyright`: văn bản có phiên bản `2026-10-19.1`, thông tin bên vận hành lấy từ cấu hình. Thiếu cấu hình thì hiển thị rõ bản dự thảo, không bịa tên/email/địa chỉ.
- Đăng ký cần ngày sinh người chơi, hai ô đồng ý riêng không tích sẵn, phiên bản đúng ở server. Lưu bản ghi đồng ý, thời điểm, hash và toàn bộ nội dung văn bản cùng thông tin bên vận hành tại thời điểm chấp thuận. Không thu thêm IP để làm bằng chứng đồng ý.
- Tài khoản cũ phải bổ sung đồng ý/độ tuổi trước khi đăng bài, bình luận, dự đoán, tim và tải ảnh. Không tự ghi nhận tài khoản cũ đã đồng ý.
- Người chơi dưới 18 tuổi dùng tài khoản được người đại diện quản lý. Đây là lựa chọn sản phẩm cho toàn bộ nhóm dưới 18, không phải tuyên bố mọi yêu cầu pháp luật đều có cùng mốc 18 tuổi. Cha/mẹ/người đại diện nhận liên kết email 48 giờ, xác nhận tư cách, ngày sinh người đại diện, bí danh công khai, đồng ý chính sách và đặt mật khẩu quản lý mới. Người chơi từ đủ 7 tuổi cần thêm xác nhận người đại diện đã giải thích và có sự đồng ý của người chơi.
- Liên kết ngẫu nhiên chỉ nằm trong email, hash ở database, không trả URL/token qua API đăng ký. Token ở fragment để không xuất hiện trong access log/Referer. Dùng một lần, có kiểm tra hết hạn và giao dịch khi nhận xác nhận. Mật khẩu quản lý thay mật khẩu trước đó; không trả phiên đăng nhập của trẻ từ trang xác nhận. Email quản lý trở thành email của người đại diện. Email đã quản lý tài khoản khác được chuyển sang hỗ trợ, chưa tự liên kết thêm trẻ.
- Chưa cấu hình SMTP hoặc gửi lỗi thì không tạo/kích hoạt tài khoản dưới 18 tuổi. Test chỉ mô phỏng gửi email, chưa gửi email thật. Cấu hình SMTP chỉ chấp nhận STARTTLS hoặc TLS và kiểm tra chứng thư.
- Tài khoản được quản lý không dùng GPS trong bản thử nghiệm, cả ở UI và API. Chính sách bản thử nghiệm không cho đăng thông tin/ảnh nhận diện trẻ em dưới 16 tuổi; **chưa có công cụ tự phát hiện khuôn mặt/tuổi hoặc kiểm duyệt tự động để bảo đảm điều này**.
- Tải ảnh/đăng bài/avatar cần xác nhận quyền sử dụng ảnh; API cũng kiểm tra, có bản ghi xác nhận theo tài khoản, tài nguyên và phiên bản. Điều khoản ghi trách nhiệm người đăng theo pháp luật và vẫn giữ nghĩa vụ riêng của nền tảng.
- `/support`: tiếp nhận phản ánh bản quyền/quyền hình ảnh, an toàn, truy cập, xóa và rút đồng ý, không cần tài khoản. Lưu yêu cầu và trả mã tham chiếu; không công khai hồ sơ. Có giới hạn 5 yêu cầu/email/giờ, chưa thay thế biện pháp chống spam ở hạ tầng.
- Có nút rút đồng ý: dừng tài khoản, ghi thời điểm rút, thu hồi token; ẩn bài/bình luận/hồ sơ khỏi API công khai, chặn phục vụ ảnh gốc của tài khoản đã dừng. **Chưa tự xóa dữ liệu database/file và không thu hồi được bản sao người khác đã có**. Yêu cầu quyền dữ liệu/gỡ nội dung cần nhân sự thực sự xử lý theo pháp luật.

## Thông tin/chức năng còn cần hoàn thiện trước công khai

1. **Định danh bên vận hành:** tên cá nhân/pháp nhân, địa chỉ, đầu mối tiếp nhận, email thực sự được theo dõi; nhà cung cấp lưu trữ/email/backup, nơi xử lý và có chuyển ra nước ngoài hay không. Cấu hình: `LEGAL_OPERATOR_NAME`, `LEGAL_OPERATOR_ADDRESS`, `LEGAL_CONTACT_EMAIL`, `LEGAL_HOSTING_LOCATION`, `LEGAL_SERVICE_PROVIDERS`.
2. **Phân loại dịch vụ và thủ tục liên quan:** trò chơi điện tử trên mạng, mạng xã hội hoặc mô hình khác; đánh giá giấy phép/xác nhận/thông báo, thông tin tài khoản phải thu thập và xác thực, yêu cầu riêng về người chưa thành niên, quản lý thời gian/nội dung chơi. App hiện chưa có xác thực SĐT/danh tính theo yêu cầu chuyên ngành. Email + checkbox không thay thế các yêu cầu này.
3. **Xác minh người đại diện:** luồng email chỉ xác nhận hộp thư và lời khai, chưa xác thực tuổi, danh tính, quyền đại diện hoặc quan hệ gia đình. Cần cơ chế xác minh hợp lệ, xử lý trường hợp tranh chấp, thay người đại diện, trẻ đủ 18 tuổi, nhiều trẻ cùng người đại diện và thu hồi chấp thuận. Không yêu cầu người dùng đăng giấy tờ tùy thân công khai; việc thu thập giấy tờ cần căn cứ và kênh an toàn, theo hạn chế pháp luật tương ứng.
4. **Quy trình xử lý dữ liệu:** cơ sở xử lý từng mục đích, dữ liệu nhạy cảm/vị trí, quyền của trẻ em, hồ sơ đánh giá tác động, chuyển dữ liệu ra nước ngoài nếu có, hợp đồng bên xử lý, kiểm soát nhân sự truy cập, lưu giữ bắt buộc theo phân loại dịch vụ, thông báo/xử lý sự cố. Không công bố SLA hoặc thời hạn lưu/xóa không đúng thực tế.
5. **Hạ tầng thật:** HTTPS, `PUBLIC_BASE_URL` đúng tên miền, SMTP thật, phân quyền quản trị, giới hạn request/upload, sao lưu, bảo mật database và email. Local không tự đọc `.env` khi chạy uvicorn thông thường; dùng `uvicorn app.main:app --env-file .env --reload` hoặc biến môi trường. Compose đã truyền biến cấu hình.
6. **Thực hiện yêu cầu:** phải có nhân sự theo dõi hàng đợi và quy trình xác minh, phản hồi, gỡ nội dung, xóa dữ liệu/file/bản sao lưu, giải quyết khiếu nại. Chưa có màn hình quản trị, cơ chế tự gỡ bài, tự xóa tài khoản, dọn ảnh thừa, dọn lượt gửi/token hết hạn hay dọn tài khoản chờ người đại diện đã quá hạn. CLI chỉ giúp đọc/đánh dấu hồ sơ, không làm các việc này thay người vận hành.
7. **Rà soát văn bản và quyền người dùng:** không có điều khoản miễn mọi trách nhiệm của JinHunt, không tước quyền khiếu nại/khởi kiện hay coi ghi nguồn ảnh là đủ quyền sử dụng. Cần kiểm tra điều kiện giao dịch chung/bảo vệ người tiêu dùng và các nghĩa vụ riêng khi bổ sung quảng cáo, thanh toán, phần thưởng hoặc phát hành ở quốc gia khác.

## Xử lý hàng đợi (chỉ operator có quyền database)

```sh
docker compose exec api python -m app.manage_legal list
docker compose exec api python -m app.manage_legal show MA_THAM_CHIEU
# Chỉ đánh dấu SAU khi đã thực sự giải quyết và phản hồi:
docker compose exec api python -m app.manage_legal close MA_THAM_CHIEU --processed
# Theo yêu cầu hợp lệ, gửi lại liên kết người đại diện:
docker compose exec api python -m app.manage_legal resend-guardian TEN_DANG_NHAP
```

Không sao chép đầu ra chứa email/nội dung yêu cầu vào log công khai hoặc issue GitHub. Không có API đọc hàng đợi công khai. Lệnh `close` không tự xóa/gỡ dữ liệu. Nếu gặp vi phạm cần gỡ, operator phải áp dụng quy trình lưu bằng chứng/hạn chế/xóa phù hợp; không xóa cả volume hoặc toàn database để giải quyết một yêu cầu.

## Phiên bản và cập nhật

Khi thay đổi quan trọng, tạo phiên bản mới ở `app/legal_docs.py`, lưu lại bản cũ và thông báo/lấy lại đồng ý phù hợp. `notice_snapshot` lưu cả văn bản và hash, không chỉ dựa vào phiên bản Git. Không backfill bản ghi đồng ý cho tài khoản cũ. Khi triển khai thay đổi model, sao lưu trước; migration bổ sung cột/bảng, không xóa dữ liệu cũ.

## Nguồn đối chiếu (kiểm tra ngày 19/10/2026)

- [Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15](https://vanban.chinhphu.vn/?docid=214590&pageid=27160).
- [Quy định về dữ liệu của trẻ em — Cổng TTĐT Chính phủ](https://xaydungchinhsach.chinhphu.vn/quy-dinh-bao-ve-du-lieu-ca-nhan-cua-tre-em-nguoi-bi-mat-hoac-han-che-nang-luc-hanh-vi-dan-su-119250725165056743.htm).
- [Nghị định 147/2024/NĐ-CP](https://vanban.chinhphu.vn/?docid=211654&pageid=27160); [hướng dẫn điều kiện dịch vụ trò chơi trên mạng, tài khoản người dưới 16 tuổi](https://chinhsachonline.chinhphu.vn/dieu-kien-cung-cap-dich-vu-tro-choi-dien-tu-tren-mang-91976.htm).
- [Bộ luật Dân sự 91/2015/QH13](https://vanban.chinhphu.vn/default.aspx?docid=183188&pageid=27160), đặc biệt quyền đối với hình ảnh và đời sống riêng tư.
- [Luật sửa đổi Luật Sở hữu trí tuệ 131/2025/QH15, hiệu lực 01/04/2026](https://vanban.chinhphu.vn/?docid=216511&pageid=27160).

Các nguồn là căn cứ rà soát, không thay cho việc kiểm tra văn bản hợp nhất/hướng dẫn đang áp dụng và tư vấn theo hồ sơ thực tế của bên vận hành.
