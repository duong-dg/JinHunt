/* Explicit, versioned consent. No checkbox is preselected. */
let currentLegalVersion = null;
function consentFields() {
  return `<fieldset class="consent-fields"><legend>Điều kiện sử dụng & quyền riêng tư</legend><label>Ngày sinh người chơi<input type="date" name="player_birth_date" required></label><div class="guardian-request" hidden><label>Email cha/mẹ hoặc người đại diện<input name="guardian_email" type="email" maxlength="254" autocomplete="email"></label><p class="muted">Dưới 18 tuổi: tạo tài khoản do người đại diện quản lý, chờ xác nhận qua email và đặt mật khẩu. Không tự đăng nhập trước khi được xác nhận. Không dùng thông tin thật của trẻ làm bí danh công khai.</p></div><label class="consent-check"><input type="checkbox" name="terms_accepted" required><span>Tôi đã đọc và chấp nhận <a href="/terms" target="_blank" rel="noopener noreferrer">Điều khoản sử dụng</a> và <a href="/copyright" target="_blank" rel="noopener noreferrer">quy tắc đăng ảnh/bản quyền</a>.</span></label><label class="consent-check"><input type="checkbox" name="privacy_accepted" required><span>Tôi đồng ý xử lý dữ liệu cần thiết để tạo, quản lý tài khoản và cung cấp dịch vụ theo <a href="/privacy" target="_blank" rel="noopener noreferrer">Chính sách quyền riêng tư</a>. Không bao gồm quảng cáo hoặc theo dõi ngoài dịch vụ.</span></label><p class="muted">Dưới 18 tuổi, đây là yêu cầu gửi người đại diện; chỉ sự chấp thuận hợp lệ của người đại diện mới kích hoạt tài khoản được quản lý.</p></fieldset>`;
}
contacts.insertAdjacentHTML('beforeend',consentFields());
contacts.querySelectorAll('.consent-fields input').forEach(input => input.disabled=true);
const registerBirthday=$('#auth-form [name=player_birth_date]');
function clientAge(value) { const born=new Date(value+'T00:00:00'); if (!value || Number.isNaN(born.getTime())) return null; const now=new Date(); return now.getFullYear()-born.getFullYear()-((now.getMonth()<born.getMonth() || (now.getMonth()===born.getMonth() && now.getDate()<born.getDate()))?1:0); }
function updateConsentAge(form, registering=false) {
  const birthday=form.elements.player_birth_date, minor=(!registering || registerMode) && clientAge(birthday.value)!==null && clientAge(birthday.value)<18;
  const guardian=form.querySelector('.guardian-request'), email=form.elements.guardian_email;
  guardian.hidden=!minor; email.disabled=!minor || (registering && !registerMode); email.required=minor;
  if (registering) {
    for (const key of ['email','phone','password']) { const input=form.elements[key]; input.disabled=minor || (key!=='password' && !registerMode); input.closest('label').hidden=minor; }
    form.elements.password.required=!minor;
  }
}
registerBirthday.onchange=()=>updateConsentAge($('#auth-form'),true);
$('#auth-switch').addEventListener('click',()=>updateConsentAge($('#auth-form'),true));
async function consentPayload(form) {
  if (!currentLegalVersion) currentLegalVersion=(await api('/legal')).version;
  const f=new FormData(form), body={legal_version:currentLegalVersion,player_birth_date:f.get('player_birth_date'),terms_accepted:form.elements.terms_accepted.checked,privacy_accepted:form.elements.privacy_accepted.checked};
  if (f.get('guardian_email')) body.guardian_email=String(f.get('guardian_email')).trim();
  if (!body.terms_accepted || !body.privacy_accepted) throw new Error('Cần chủ động đồng ý điều khoản và xử lý dữ liệu cần thiết.');
  return body;
}
document.body.insertAdjacentHTML('beforeend',`<dialog id="consent-dialog"><button class="close" aria-label="Đóng">×</button><p class="eyebrow">HOÀN THIỆN ĐIỀU KIỆN THAM GIA</p><h2>Xác nhận điều khoản & độ tuổi</h2><p class="muted">Tài khoản cũ vẫn được giữ. Trước khi đăng bài hoặc tương tác, hãy xác nhận chính sách hiện tại. Người dưới 18 tuổi chuyển sang tài khoản do người đại diện quản lý.</p><form id="consent-form">${consentFields()}<button class="primary" type="submit">Xác nhận / gửi người đại diện</button></form></dialog><dialog id="withdraw-dialog"><button class="close" aria-label="Đóng">×</button><p class="eyebrow">LỰA CHỌN QUYỀN RIÊNG TƯ</p><h2>Rút lại sự đồng ý</h2><p>Thao tác này dừng tài khoản và thu hồi các phiên đăng nhập. Dữ liệu chưa tự động xóa. Bạn vẫn có thể dùng <a href="/support?kind=deletion" target="_blank" rel="noopener">biểu mẫu hỗ trợ</a> để yêu cầu xóa dữ liệu hoặc xử lý tiếp.</p><form id="withdraw-form"><label class="consent-check"><input type="checkbox" required><span>Tôi hiểu tài khoản sẽ dừng hoạt động và muốn rút lại sự đồng ý xử lý dữ liệu.</span></label><button class="primary" type="submit">Rút đồng ý & dừng tài khoản</button></form></dialog>`);
setupDialog($('#consent-dialog')); setupDialog($('#withdraw-dialog'));
$('#consent-form [name=player_birth_date]').onchange=()=>updateConsentAge($('#consent-form'));
updateConsentAge($('#consent-form'));
function openConsentDialog() { if (!$('#consent-dialog').open) $('#consent-dialog').showModal(); }
$('#consent-form').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;busy(form,async()=>{
  const result=await api('/me/legal-consent',{method:'POST',body:await consentPayload(form)});
  $('#consent-dialog').close();
  if (result.status==='pending_guardian') {token='';user=null;sessionStorage.removeItem('jinhunt-token');renderUser();toast(result.message);}
  else {await refreshUser();toast('Đã ghi nhận phiên bản điều khoản và quyền riêng tư bạn chấp thuận.');}
});};
$('#create-form [type=submit]').insertAdjacentHTML('beforebegin','<label class="consent-check content-rights"><input type="checkbox" name="content_rights_confirmed" required><span>Tôi có quyền sử dụng và đăng ảnh này; đã có sự cho phép cần thiết về hình ảnh/quyền riêng tư và chịu trách nhiệm về nội dung theo pháp luật. Tôi đã đọc <a href="/copyright" target="_blank" rel="noopener noreferrer">quy tắc bản quyền</a>. Không đăng thông tin nhận diện trẻ em dưới 16 tuổi trong bản thử nghiệm.</span></label>');
$('.avatar-editor').insertAdjacentHTML('afterend','<label class="consent-check avatar-rights"><input type="checkbox" id="avatar-rights"><span>Tôi có quyền sử dụng và công khai ảnh đại diện này theo <a href="/copyright" target="_blank" rel="noopener noreferrer">quy tắc bản quyền</a>; không dùng ảnh nhận diện trẻ em dưới 16 tuổi trong bản thử nghiệm.</span></label>');
$('#profile-form').insertAdjacentHTML('afterend','<div class="privacy-actions"><a href="/privacy" target="_blank" rel="noopener noreferrer">Đọc chính sách quyền riêng tư ↗</a><a href="/support?kind=deletion" target="_blank" rel="noopener noreferrer">Yêu cầu xóa / nhận bản sao dữ liệu ↗</a><button type="button" id="review-consent" class="text-button">Xem / xác nhận điều khoản hiện tại</button><button type="button" id="withdraw-consent" class="text-button">Rút lại sự đồng ý xử lý dữ liệu</button></div>');
$('#review-consent').onclick=()=>{$('#profile-dialog').close();openConsentDialog();};
$('#withdraw-consent').onclick=()=>{$('#profile-dialog').close();$('#withdraw-dialog').showModal();};
$('#withdraw-form').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;busy(form,async()=>{const result=await api('/me/withdraw-consent',{method:'POST'});token='';user=null;sessionStorage.removeItem('jinhunt-token');$('#withdraw-dialog').close();renderUser();loadFeed();toast(result.message);});};
document.body.insertAdjacentHTML('beforeend','<nav class="legal-footer" aria-label="Điều khoản và quyền riêng tư"><a href="/terms" target="_blank" rel="noopener noreferrer">Điều khoản</a><a href="/privacy" target="_blank" rel="noopener noreferrer">Quyền riêng tư</a><a href="/copyright" target="_blank" rel="noopener noreferrer">Bản quyền & đăng ảnh</a><a href="/support" target="_blank" rel="noopener noreferrer">Yêu cầu hỗ trợ</a></nav>');
api('/legal').then(config=>{currentLegalVersion=config.version;if(config.draft){const hint=document.createElement('p');hint.className='legal-draft-hint';hint.textContent='Chính sách đang ở bản dự thảo; thông tin đơn vị vận hành đang được hoàn thiện.';$('.legal-footer').after(hint);}}).catch(()=>{});
if (user?.needs_legal_consent) openConsentDialog();
