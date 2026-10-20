const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function readSessionToken() {
  try {
    const saved = localStorage.getItem('jinhunt-token') || sessionStorage.getItem('jinhunt-token') || '';
    if (saved) localStorage.setItem('jinhunt-token', saved);
    sessionStorage.removeItem('jinhunt-token');
    return saved;
  } catch { return sessionStorage.getItem('jinhunt-token') || ''; }
}
function saveSessionToken(value) {
  sessionStorage.removeItem('jinhunt-token');
  try {
    if (value) localStorage.setItem('jinhunt-token', value);
    else localStorage.removeItem('jinhunt-token');
  } catch { if (value) sessionStorage.setItem('jinhunt-token', value); }
}
let token = readSessionToken(), user = null, registerMode = false, page = 'explore', toastTimer;
let feedOffset = 0;
let inboxNext = null, inboxThroughId = 0, inboxLoading = false;
const iconPaths = {home:'M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z',award:'m12 3 3 6 6 1-4.5 4.5 1 6.5-5.5-3-5.5 3 1-6.5L3 10l6-1Z',plus:'M12 5v14M5 12h14',user:'M20 21v-2a7 7 0 0 0-14 0v2M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',camera:'M3 7h4l2-3h6l2 3h4v13H3ZM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0',compass:'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0ZM16 8l-3 5-5 3 3-5Z',chat:'M21 11a9 9 0 0 1-9 9H4l-3 2 2-6a9 9 0 1 1 18-5Z',pin:'M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0ZM15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0'};
function icon(name) { return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${iconPaths[name] || iconPaths.compass}"/></svg>`; }
iconPaths.heart = 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z';
iconPaths.bell = 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4';
$('#ranking').insertAdjacentHTML('afterend','<button id="notifications-button"><span data-icon="bell"></span><span>Thông báo <b id="unread-count" hidden></b></span></button>');
document.body.insertAdjacentHTML('beforeend','<dialog id="notifications-dialog" class="inbox-dialog"><button class="close" aria-label="Đóng">×</button><p class="eyebrow">KẾT NỐI CÙNG CỘNG ĐỒNG</p><h2>Thông báo của bạn</h2><button type="button" id="notifications-read" class="outline">Đánh dấu tất cả đã đọc</button><div id="notifications-list" aria-live="polite"></div><button type="button" id="notifications-more" class="outline" hidden>Xem thông báo cũ hơn</button></dialog>');
$('#notifications-read').insertAdjacentHTML('afterend','<button type="button" id="notifications-refresh" class="outline">Làm mới</button>');
const inboxPage = document.createElement('section');
inboxPage.id = 'notifications-page'; inboxPage.hidden = true;
inboxPage.setAttribute('aria-label','Thông báo');
while ($('#notifications-dialog').children.length) inboxPage.append($('#notifications-dialog').firstElementChild);
inboxPage.querySelector('.close').remove();
$('main').append(inboxPage);
$('#notifications-dialog').remove();
const screenHeader = document.createElement('div'); screenHeader.className = 'screen-header';
screenHeader.innerHTML = '<button type="button" id="screen-back" aria-label="Quay lại bảng tin">‹</button><strong id="screen-title"></strong>';
$('main').prepend(screenHeader);
function showMainPage(next) {
  page = next;
  const inbox = next === 'notifications';
  inboxPage.hidden = !inbox;
  document.querySelectorAll('main > :not(#notifications-page):not(.screen-header)').forEach(el => el.classList.toggle('page-hidden',inbox));
  document.body.classList.toggle('subpage',next !== 'explore');
  $('#screen-title').textContent = inbox ? 'Thông báo' : next === 'ranking' ? 'Bảng xếp hạng' : 'Bảng tin';
  for (const [id,key] of [['explore','explore'],['ranking','ranking'],['notifications-button','notifications']]) {
    const button = $('#'+id), active = next === key;
    button.classList.toggle('active',active);
    if(active) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current');
  }
}
$('#screen-back').onclick = () => { showMainPage('explore'); loadFeed(); window.scrollTo(0,0); };
const inboxTools = document.createElement('div'); inboxTools.className = 'inbox-tools'; $('#notifications-read').before(inboxTools); inboxTools.append($('#notifications-read'),$('#notifications-refresh'));
function avatarContent(name, url) { const initial = esc(Array.from(name || 'J')[0].toUpperCase()); return /^\/uploads\/[a-zA-Z0-9-]+\.jpg$/.test(url || '') ? `<img src="${esc(url)}" alt="" loading="lazy" data-fallback="${initial}">` : initial; }
function avatar(name, url, extra = '') { return `<span class="avatar ${extra}">${avatarContent(name, url)}</span>`; }
document.addEventListener('error', event => { if (event.target.matches?.('.avatar img')) event.target.parentElement.textContent = event.target.dataset.fallback || 'J'; }, true);
document.querySelectorAll('[data-icon]').forEach(element => element.innerHTML = icon(element.dataset.icon));
const contacts = document.createElement('div');
contacts.id = 'register-contacts'; contacts.hidden = true;
contacts.innerHTML = '<label>Tên hiển thị<input name="display_name" maxlength="80" autocomplete="nickname"></label><label>Email<input name="email" type="email" maxlength="254" autocomplete="email"></label><label>Số điện thoại<input name="phone" type="tel" maxlength="40" autocomplete="tel" placeholder="0901234567 hoặc +84901234567"></label><p class="muted">Cần email hoặc số điện thoại. Hiện chưa xác minh bằng email/OTP.</p>';
$('#auth-submit').before(contacts);
const loginInput = $('#auth-form [name=username]');
loginInput.removeAttribute('pattern'); loginInput.maxLength = 254;
loginInput.placeholder = 'Tên đăng nhập, email hoặc số điện thoại';
document.body.insertAdjacentHTML('beforeend', '<dialog id="profile-dialog"><button class="close" aria-label="Đóng">×</button><p class="eyebrow">HỒ SƠ CỦA BẠN</p><h2>Thông tin cá nhân</h2><form id="profile-form"><label>Tên hiển thị<input name="display_name" maxlength="80" autocomplete="nickname"></label><label>Giới thiệu<textarea name="bio" maxlength="500"></textarea></label><label>Email<input name="email" type="email" maxlength="254" autocomplete="email"></label><label>Số điện thoại<input name="phone" type="tel" maxlength="40" autocomplete="tel"></label><p class="muted">Email và số điện thoại chỉ bạn thấy, chưa được xác minh. Giữ ít nhất một thông tin liên hệ.</p><button class="primary" type="submit">Lưu thông tin</button></form><button class="text-button" id="logout">Đăng xuất</button></dialog>');
$('#profile-form').insertAdjacentHTML('beforebegin', '<section class="avatar-editor" aria-label="Ảnh đại diện"><span class="avatar self-avatar profile-avatar">J</span><div><strong>Ảnh đại diện của bạn</strong><p>Ảnh được cắt vuông; chỉ công khai sau khi được duyệt.</p><div class="avatar-actions"><button type="button" id="avatar-choose">Chọn ảnh mới</button><button type="button" id="avatar-remove" hidden>Xóa ảnh</button></div><input type="file" id="avatar-file" accept="image/jpeg,image/png,image/webp" aria-label="Chọn ảnh đại diện" hidden><p id="avatar-status" role="status" aria-live="polite"></p></div></section>');
$('#avatar-choose').onclick = () => { if (!$('#avatar-rights')?.checked) { toast('Hãy xác nhận quyền sử dụng ảnh đại diện trước.','error'); return; } $('#avatar-file').click(); };
async function updateAvatar(remove = false) {
  const input = $('#avatar-file'), file = input.files[0];
  if (!remove && !file) return;
  if (!remove && !$('#avatar-rights')?.checked) { toast('Cần xác nhận quyền sử dụng ảnh đại diện.','error'); input.value=''; return; }
  $('#avatar-choose').disabled = $('#avatar-remove').disabled = true;
  $('#avatar-status').textContent = remove ? 'Đang xóa ảnh…' : 'Đang tải ảnh đại diện…';
  try {
    if (file && !remove && file.size > 8 * 1024 * 1024) throw new Error('Ảnh đại diện tối đa 8 MB.');
    const body = new FormData(); if (!remove) { body.append('file',file); body.append('rights_confirmed','true'); }
    user = await api('/me/avatar', remove ? {method:'DELETE'} : {method:'POST',body});
    renderUser(); loadHunters(); loadFeed();
    $('#avatar-status').textContent = remove ? 'Đã xóa ảnh đại diện.' : user.moderation_status==='pending' ? 'Ảnh đại diện đang chờ duyệt, chưa công khai.' : 'Đã lưu ảnh đại diện mới.';
    toast($('#avatar-status').textContent);
    if ($('#avatar-rights')) $('#avatar-rights').checked=false;
  } catch (error) { $('#avatar-status').textContent = error.message; toast(error.message,'error'); }
  finally { input.value = ''; $('#avatar-choose').disabled = $('#avatar-remove').disabled = false; }
}
$('#avatar-file').onchange = () => updateAvatar();
$('#avatar-remove').onclick = () => updateAvatar(true);
const notification = $('#toast');
notification.setAttribute('popover','manual'); notification.setAttribute('aria-live','polite');
notification.innerHTML = '<span class="notice-icon" aria-hidden="true">✓</span><div><strong id="notice-title"></strong><span id="notice-message"></span></div><button type="button" id="notice-close" aria-label="Đóng thông báo">×</button>';
function hideToast() { if (typeof notification.hidePopover === 'function' && notification.matches(':popover-open')) notification.hidePopover(); notification.hidden = true; clearTimeout(toastTimer); }
$('#notice-close').onclick = hideToast;
function toast(message, kind = 'success') {
  clearTimeout(toastTimer); notification.hidden = false; notification.dataset.kind = kind;
  const host = document.activeElement?.closest('dialog[open]') || [...document.querySelectorAll('dialog[open]')].at(-1) || document.body;
  if (notification.parentElement !== host) { if (typeof notification.hidePopover === 'function' && notification.matches(':popover-open')) notification.hidePopover(); host.append(notification); }
  $('#notice-title').textContent = kind === 'error' ? 'Chưa thực hiện được' : 'Thông báo';
  $('#notice-message').textContent = message; $('.notice-icon').textContent = kind === 'error' ? '!' : '✓';
  if (typeof notification.showPopover === 'function') { if (notification.matches(':popover-open')) notification.hidePopover(); notification.showPopover(); }
  else (document.querySelector('dialog[open]') || document.body).append(notification);
  toastTimer = setTimeout(hideToast, kind === 'error' ? 12000 : 7000);
}
function formMessage(form, message, kind = 'error') {
  let box = form.querySelector('.form-message');
  if (!box) { box = document.createElement('p'); box.className = 'form-message'; box.setAttribute('role','alert'); form.querySelector('[type=submit]').before(box); }
  box.textContent = message; box.dataset.kind = kind; box.hidden = !message;
  if (message) box.scrollIntoView({block:'nearest',behavior:'smooth'});
}
async function api(path, options = {}) {
  const requestToken = token;
  const headers = {...(requestToken ? {Authorization: `Bearer ${requestToken}`} : {}), ...options.headers};
  if (options.body && !(options.body instanceof FormData)) { headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.body); }
  let response;
  try { response = await fetch(`/api${path}`, {...options, headers}); } catch { throw new Error('Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.'); }
  let data;
  try { data = response.status === 204 ? null : await response.json(); } catch { throw new Error('Máy chủ chưa xử lý được yêu cầu. Vui lòng thử lại.'); }
  if (!response.ok) {
    if (response.status === 401 && requestToken && token === requestToken && !path.startsWith('/auth/')) { token = ''; user = null; saveSessionToken(''); renderUser(); }
    const labels = {email:'Email',phone:'Số điện thoại',username:'Tên đăng nhập',password:'Mật khẩu',display_name:'Tên hiển thị',bio:'Giới thiệu',title:'Tiêu đề',answer:'Đáp án',content:'Bình luận'};
    const message = Array.isArray(data.detail) ? data.detail.map(e => { const field = e.loc?.[e.loc.length-1], reason = e.msg?.startsWith('Value error, ') ? e.msg.slice(13) : 'Thông tin chưa hợp lệ, hãy kiểm tra lại.'; return `${labels[field] ? labels[field]+': ' : ''}${reason}`; }).join(' ') : typeof data.detail === 'string' ? data.detail : 'Chưa thực hiện được. Vui lòng thử lại.';
    throw new Error(message);
  }
  return data;
}
function renderUser() {
  window.renderStaffNav?.();
  const name = user ? user.display_name || user.username : 'Nhà khám phá mới';
  $('#account-label').textContent = user ? 'Hồ sơ của tôi' : 'Đăng nhập';
  $('#journey-name').textContent = name;
  $('#journey-handle').textContent = user ? `@${user.username}` : 'Một góc nhìn mới đang chờ bạn';
  $('#profile').textContent = user ? `Level ${user.level} · ${user.xp} XP · Còn ${200 - user.xp % 200} XP lên cấp` : 'Đăng nhập để bắt đầu tích lũy XP';
  $('#xp-fill').style.width = `${user ? user.xp % 200 / 2 : 0}%`;
  $('.xp-track').setAttribute('aria-valuenow', user ? user.xp % 200 : 0);
  $('#journey-action').textContent = user ? 'Chỉnh sửa hồ sơ ↗' : 'Bắt đầu hành trình ↗';
  document.querySelectorAll('.self-avatar').forEach(element => element.innerHTML = avatarContent(user ? name : 'J', user?.avatar_url));
  if ($('#avatar-remove')) $('#avatar-remove').hidden = !user?.avatar_url;
  if (!user) { $('#unread-count').hidden = true; $('#notifications-list').innerHTML = ''; inboxNext = null; inboxThroughId = 0; }
  else refreshInbox();
  document.querySelectorAll('#create-form .location-picker').forEach(picker => { if (user?.guardian_managed) picker.querySelector('.clear-location').click(); picker.hidden=Boolean(user?.guardian_managed); });

}
async function refreshUser() { if (token) { try { user = await api('/me'); } catch {} } renderUser(); }
function requireLogin(consentRequired = true) { if (user) { if (consentRequired && user.needs_legal_consent) { if (typeof openConsentDialog==='function') openConsentDialog(); else toast('Cần xác nhận điều khoản và độ tuổi trong tài khoản.','error'); return false; } return true; } $('#auth-dialog').showModal(); return false; }
async function busy(form, task) { if (form.dataset.locating === 'true') { formMessage(form,'Đang lấy vị trí, vui lòng chờ hoặc bấm Hủy.'); return; } const button = form.querySelector('[type="submit"]'); button.disabled = true; formMessage(form,''); try { await task(); } catch (error) { formMessage(form,error.message); toast(error.message,'error'); } finally { button.disabled = false; } }
const locationRequests = new WeakMap();
function locationMarkup(forGuess = false) {
  if (forGuess && user?.guardian_managed) return '<p class="muted">Tài khoản được người đại diện quản lý dự đoán bằng tên, chưa dùng GPS.</p>';
  return `<section class="location-picker"><h3>${forGuess ? 'Hoặc xác nhận bằng vị trí của bạn' : 'Vị trí địa điểm trong ảnh (tùy chọn)'}</h3><p class="muted">${forGuess ? 'Nếu bạn đang ở nơi trong ảnh, dùng vị trí máy để gửi dự đoán.' : 'Chỉ lấy vị trí máy khi bạn đang ở đúng nơi chụp ảnh. Bạn vẫn đăng được bằng đáp án tên địa danh.'}</p><input type="hidden" name="latitude"><input type="hidden" name="longitude"><div class="location-actions"><button type="button" class="locate-button">${icon('pin')} Lấy vị trí hiện tại</button><button type="button" class="clear-location" hidden>Bỏ vị trí</button></div><p class="location-status" role="status" aria-live="polite">Chưa đính kèm vị trí.</p></section>`;
}
function bindLocation(form) {
  const picker = form.querySelector('.location-picker');
  if (!picker) return;
  const locate = picker.querySelector('.locate-button'), clear = picker.querySelector('.clear-location'), status = picker.querySelector('.location-status');
  const latitude = form.elements.latitude, longitude = form.elements.longitude;
  const invalidate = () => { locationRequests.set(form, Symbol()); form.dataset.locating = 'false'; locate.disabled = false; locate.innerHTML = `${icon('pin')} Lấy vị trí hiện tại`; };
  const reset = () => { invalidate(); latitude.value = ''; longitude.value = ''; clear.hidden = true; clear.textContent = 'Bỏ vị trí'; status.textContent = 'Chưa đính kèm vị trí.'; };
  clear.onclick = reset;
  locate.onclick = () => {
    reset();
    if (!window.isSecureContext) { status.textContent = 'Cần mở trang bằng HTTPS để lấy vị trí. Bạn vẫn có thể dùng đáp án tên địa danh.'; return; }
    if (!navigator.geolocation) { status.textContent = 'Trình duyệt không hỗ trợ lấy vị trí. Bạn vẫn có thể dùng tên địa danh.'; return; }
    const request = Symbol(); locationRequests.set(form, request);
    form.dataset.locating = 'true'; locate.disabled = true; locate.textContent = 'Đang lấy vị trí…'; clear.textContent = 'Hủy'; clear.hidden = false;
    status.textContent = 'Hãy cho phép quyền vị trí khi trình duyệt hỏi.';
    const active = () => locationRequests.get(form) === request && form.isConnected && form.closest('dialog').open;
    const finish = () => { invalidate(); clear.textContent = 'Bỏ vị trí'; };
    navigator.geolocation.getCurrentPosition(position => {
      if (!active()) return;
      finish();
      const {latitude: lat, longitude: lng, accuracy} = position.coords;
      if (!Number.isFinite(lat) || !Number.isFinite(lng) || !Number.isFinite(accuracy) || accuracy > 150) { clear.hidden = true; status.textContent = 'Vị trí chưa đủ chính xác. Hãy bật định vị chính xác, ra nơi thoáng rồi thử lại hoặc dùng tên địa danh.'; return; }
      latitude.value = String(lat); longitude.value = String(lng);
      status.textContent = `Đã lấy vị trí máy · Sai số khoảng ${Math.ceil(accuracy)} m. Chỉ dùng nếu đây là địa điểm bạn muốn chọn.`;
    }, error => {
      if (!active()) return;
      finish(); clear.hidden = true;
      status.textContent = ({1:'Bạn chưa cho phép vị trí. Mở quyền vị trí trong trình duyệt để thử lại, hoặc dùng tên địa danh.',2:'Chưa xác định được vị trí. Bật định vị trên máy rồi thử lại.',3:'Lấy vị trí quá lâu. Hãy thử lại ở nơi thoáng hơn.'})[error.code] || 'Không lấy được vị trí. Hãy thử lại hoặc dùng tên địa danh.';
    }, {enableHighAccuracy:true, timeout:15000, maximumAge:0});
  };
  form.addEventListener('reset', reset);
}
$('#create-form details').outerHTML = locationMarkup();
bindLocation($('#create-form'));
$('#create-form [name=answer]').closest('label').insertAdjacentHTML('afterend','<label>Tên gọi khác được chấp nhận (tùy chọn)<textarea name="aliases" maxlength="2000" placeholder="Mỗi dòng một tên, ví dụ: Chợ Bến Thành&#10;Ben Thanh Market"></textarea></label><p class="muted">Tối đa 10 tên. Hệ thống khớp cả cụm tên, không phân biệt dấu và hoa/thường.</p>');
function likeMarkup(c) { return `<button type="button" class="like-button ${c.liked_by_me ? 'is-liked' : ''}" data-like-case="${c.id}" data-liked="${Boolean(c.liked_by_me)}" aria-pressed="${Boolean(c.liked_by_me)}" aria-label="${c.liked_by_me ? 'Bỏ tim' : 'Thả tim'} bài viết">${icon('heart')}<span>${c.likes || 0}</span></button>`; }
function bindLikes(root = document) { root.querySelectorAll('[data-like-case]').forEach(button => button.onclick = () => toggleLike(button)); }
async function toggleLike(button) {
  if (!requireLogin()) return;
  const id = Number(button.dataset.likeCase), liked = button.dataset.liked === 'true';
  document.querySelectorAll(`[data-like-case="${id}"]`).forEach(b => b.disabled = true);
  try {
    const result = await api(`/cases/${id}/like`,{method:liked ? 'DELETE' : 'PUT'});
    document.querySelectorAll(`[data-like-case="${id}"]`).forEach(b => { b.dataset.liked = String(result.liked_by_me); b.classList.toggle('is-liked',result.liked_by_me); b.setAttribute('aria-pressed',String(result.liked_by_me)); b.setAttribute('aria-label',result.liked_by_me ? 'Bỏ tim bài viết' : 'Thả tim bài viết'); b.querySelector('span').textContent = result.likes; });
  } catch (error) { toast(error.message,'error'); }
  finally { document.querySelectorAll(`[data-like-case="${id}"]`).forEach(b => b.disabled = false); }
}
async function refreshInbox(append = false) {
  if (!user || inboxLoading || (append && !inboxNext)) return;
  const account = user.id; inboxLoading = true;
  try {
    const result = await api(`/notifications${append ? '?before_id='+inboxNext : ''}`);
    if (user?.id !== account) return;
    const count = result.unread_count || 0;
    $('#unread-count').textContent = count > 99 ? '99+' : count; $('#unread-count').hidden = !count;
    $('#notifications-button').setAttribute('aria-label', `Thông báo, ${count} chưa đọc`);
    if (!append) inboxThroughId = result.items[0]?.id || 0;
    inboxNext = result.next_before_id;
    const verbs = {like:'đã thả tim bài viết của bạn',comment:'đã bình luận vào bài viết của bạn',solve:'đã giải đúng thử thách của bạn'};
    const markup = result.items.map(n => `<button type="button" class="inbox-item ${n.is_read ? '' : 'unread'}" data-notification="${n.id}" data-notification-case="${n.case_id}">${avatar(n.actor.display_name || n.actor.username,n.actor.avatar_url)}<span><span><strong>${esc(n.actor.display_name || n.actor.username)}</strong> ${verbs[n.kind] || 'đã tương tác với bài viết của bạn'}.</span><b class="inbox-case">${esc(n.case_title)}</b><small>${esc(new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(n.created_at) ? n.created_at : n.created_at+'Z').toLocaleString('vi-VN'))}</small></span><i aria-label="Chưa đọc"></i></button>`).join('');
    if (append) $('#notifications-list').insertAdjacentHTML('beforeend',markup); else $('#notifications-list').innerHTML = markup || '<p class="inbox-empty">Chưa có thông báo. Khi có người thả tim, bình luận hoặc giải đúng bài của bạn, bạn sẽ thấy ở đây.</p>';
    $('#notifications-more').hidden = !inboxNext; $('#notifications-read').disabled = !count;
    document.querySelectorAll('[data-notification]').forEach(b => b.onclick = async () => { b.disabled = true; try { await api(`/notifications/${b.dataset.notification}/read`,{method:'POST'}); await openCase(Number(b.dataset.notificationCase),true); refreshInbox(); } catch(error) { toast(error.message,'error'); } finally { b.disabled = false; } });
  } catch (error) { if (page === 'notifications') { $('#notifications-list').innerHTML = '<p class="inbox-empty">Chưa tải được thông báo. Bấm Làm mới để thử lại.</p>'; toast(error.message,'error'); } }
  finally { inboxLoading = false; }
}
$('#notifications-button').onclick = () => { if (requireLogin(false)) { showMainPage('notifications'); window.scrollTo(0,0); refreshInbox(); } };
$('#notifications-more').onclick = () => refreshInbox(true);
$('#notifications-refresh').onclick = () => refreshInbox();
$('#notifications-read').onclick = async () => { if (!inboxThroughId) return; $('#notifications-read').disabled = true; try { await api('/notifications/read',{method:'POST',body:{through_id:inboxThroughId}}); await refreshInbox(); } catch(error) { $('#notifications-read').disabled = false; toast(error.message,'error'); } };
setInterval(() => { if (!document.hidden && user && page !== 'notifications') refreshInbox(); },30000);
document.addEventListener('visibilitychange', () => { if (!document.hidden && user) refreshInbox(); });
async function loadFeed(append = false) {
  if (page === 'notifications') return;
  showMainPage(page);
  if (!append) feedOffset = 0;
  $('#load-more').hidden = true;
  $('#explore').classList.toggle('active', page === 'explore'); $('#ranking').classList.toggle('active', page === 'ranking');
  for (const [id, active] of [['explore', page === 'explore'], ['ranking', page === 'ranking']]) { if (active) $('#' + id).setAttribute('aria-current','page'); else $('#' + id).removeAttribute('aria-current'); }
  $('#section-title').textContent = page === 'explore' ? 'Đi tìm nơi chốn.' : 'Dấu chân khám phá.';
  $('#feed-label').textContent = page === 'explore' ? 'Mới nhất từ cộng đồng' : 'Bảng xếp hạng · Tổng XP';
  $('.composer').hidden = page !== 'explore';
  if (!append) $('#feed').innerHTML = '<div class="empty">Đang tải hành trình…</div>';
  try {
    if (page === 'ranking') { const rows = await api('/leaderboard'); $('#feed').innerHTML = rows.length ? rows.map((u,i) => `<div class="leader"><span>${String(i+1).padStart(2,'0')}</span>${avatar(u.display_name || u.username,u.avatar_url)}<strong>${esc(u.display_name || u.username)}</strong><span class="score">Level ${u.level} · ${u.xp} XP</span></div>`).join('') : '<div class="empty">Bảng xếp hạng đang chờ nhà khám phá đầu tiên.</div>'; return; }
    const rows = await api(`/cases?offset=${feedOffset}&limit=12`);
    const markup = rows.map(c => `<article class="post"><div class="post-header">${avatar(c.creator_display_name || c.creator,c.creator_avatar_url)}<div><strong>${esc(c.creator_display_name || c.creator)}</strong><span>Đã chia sẻ một địa điểm bí ẩn</span></div><span class="post-reward">+${c.reward_xp} XP</span></div><div class="photo-frame"><button class="post-photo" data-case="${c.id}" aria-label="Xem thử thách ${esc(c.title)}"><img src="${esc(c.image_url)}" alt="Ảnh thử thách ${esc(c.title)}" loading="lazy"></button><button type="button" class="photo-report" data-report-case="${c.id}" aria-label="Báo cáo ảnh vi phạm" title="Báo cáo ảnh vi phạm"><span aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M5 21V4m0 0c5-4 9 4 14 0v10c-5 4-9-4-14 0"/></svg></span></button></div><div class="post-body"><div class="post-actions">${likeMarkup(c)}<button class="guess-button" data-case="${c.id}" data-discussion="true">${icon('chat')}<span>Bình luận / Dự đoán · ${c.comments || 0}</span></button><span class="solved-count">${c.solves} người giải được</span></div><h2>${esc(c.title)}</h2>${c.description ? `<p class="post-description">${esc(c.description)}</p>` : '<p class="post-description muted">Nhìn kỹ bức ảnh, bạn nhận ra nơi này chứ?</p>'}<p class="private-note">${icon('compass')} Đáp án của bạn được giữ riêng tư.</p></div></article>`).join('');
    if (append) $('#feed').insertAdjacentHTML('beforeend', markup); else $('#feed').innerHTML = markup || '<div class="empty"><span class="empty-icon">◈</span><p class="eyebrow">MỖI TẤM ẢNH, MỘT HÀNH TRÌNH</p><h3>Chia sẻ góc nhìn đầu tiên</h3><p>Một con hẻm quen, một quán nhỏ ven đường…<br>Đăng ảnh và để mọi người tìm ra nơi bạn đã đến.</p><button class="primary" id="empty-create">＋ Tạo thử thách đầu tiên</button></div>';
    feedOffset += rows.length;
    $('#load-more').hidden = rows.length < 12;
    document.querySelectorAll('[data-case]').forEach(b => b.onclick = () => openCase(Number(b.dataset.case), Boolean(b.dataset.discussion)));
    bindLikes($('#feed'));
    if ($('#empty-create')) $('#empty-create').onclick = () => $('#create').click();
  } catch (error) { if (!append) { $('#feed').innerHTML = '<div class="empty">Không tải được dữ liệu. <button id="retry">Thử lại</button></div>'; $('#retry').onclick = () => loadFeed(); } else $('#load-more').hidden = false; toast(error.message,'error'); }
}
async function loadHunters() { try { const rows = (await api('/leaderboard')).slice(0, 4); $('#top-hunters').innerHTML = rows.length ? rows.map((u,i) => `<div class="hunter"><span class="hunter-rank">${i+1}</span>${avatar(u.display_name || u.username,u.avatar_url)}<div><strong>${esc(u.display_name || u.username)}</strong><span>Level ${u.level} · ${u.xp} XP</span></div></div>`).join('') : '<p class="muted">Cộng đồng đang chờ nhà khám phá đầu tiên. Có thể là bạn!</p>'; } catch { $('#top-hunters').innerHTML = '<p class="muted">Chưa tải được bảng xếp hạng.</p>'; } }
async function loadComments(id) { const rows = await api(`/cases/${id}/comments`); $('#comments').innerHTML = rows.length ? rows.map(c => `<div class="comment ${c.is_hidden ? 'hidden-comment' : ''}">${avatar(c.display_name || c.username,c.avatar_url)}<div class="comment-body"><strong>${esc(c.display_name || c.username)}</strong><p>${esc(c.content)}</p>${c.is_hidden ? '<span class="comment-hidden-label">Nội dung được giữ riêng tư</span>' : ''}</div></div>`).join('') : '<p class="muted">Chưa có trao đổi. Hãy bắt đầu với một gợi ý!</p>'; }
async function openCase(id, discussion = false) {
  try {
    const c = await api(`/cases/${id}`);
    $('#detail').innerHTML = `<p class="eyebrow">THỬ THÁCH #${c.id} · +${c.reward_xp} XP</p><h2>${esc(c.title)}</h2><div class="detail-author">${avatar(c.creator_display_name || c.creator,c.creator_avatar_url)}<span>${esc(c.creator_display_name || c.creator)} · ${c.solves} người giải được</span>${likeMarkup(c)}<button type="button" class="report-button" data-report-case="${c.id}">Báo cáo</button></div><img class="detail-image" src="${esc(c.image_url)}" alt="Ảnh địa điểm bí ẩn"><p>${esc(c.description)}</p><hr><h3>Bình luận & dự đoán</h3><p class="muted">Cùng một ô để trao đổi hoặc đoán tên địa danh. Nội dung trùng cả cụm đáp án sẽ được che, đoán đúng nhận XP một lần.</p><div id="comments"></div><form id="comment-form"><label>Bình luận hoặc đoán địa điểm<textarea name="content" maxlength="1000" placeholder="Ví dụ: Mình nghĩ đây là Chợ Bến Thành…"></textarea></label>${c.has_coordinates ? `<details class="gps-details"><summary>Hoặc dự đoán bằng vị trí máy</summary>${locationMarkup(true)}</details>` : ''}<button class="primary" type="submit">Gửi bình luận / dự đoán ↗</button><p id="comment-result" class="muted" role="status">Trao đổi thường hiển thị công khai. Dự đoán trúng đáp án hoặc gửi bằng GPS được giữ riêng tư.</p></form>`;
    if (c.has_coordinates) bindLocation($('#comment-form'));
    bindLikes($('#detail'));
    if (!$('#detail-dialog').open) $('#detail-dialog').showModal();
    $('#comment-form').onsubmit = event => { event.preventDefault(); if (!user) { toast('Đăng nhập để gửi bình luận hoặc dự đoán.','error'); return; } const form = event.currentTarget; busy(form, async () => {
      const f = new FormData(form), body = {content:String(f.get('content') || '').trim()};
      for (const key of ['latitude','longitude']) if (f.get(key) !== null && f.get(key) !== '') body[key] = Number(f.get(key));
      if (!body.content && body.latitude === undefined) throw new Error('Nhập bình luận, tên địa danh hoặc lấy vị trí để dự đoán.');
      const usedGPS = body.latitude !== undefined, result = await api(`/cases/${id}/comments`,{method:'POST',body});
      form.reset();
      const message = result.status === 'correct' ? `Đoán đúng! Bạn nhận +${result.reward_xp} XP. Nội dung đã được che.` : result.status === 'already_solved' ? 'Bạn đã giải được bài này rồi. Nội dung có đáp án vẫn được che.' : result.status === 'author' ? 'Bạn là người đăng bài, không nhận XP. Nội dung đáp án đã được che.' : usedGPS ? 'Vị trí chưa trúng. Dự đoán của bạn vẫn được giữ riêng tư.' : result.is_hidden ? 'Nội dung chứa đáp án đã được che để tránh tiết lộ.' : 'Đã đăng bình luận.';
      $('#comment-result').textContent = message; toast(message);
      await loadComments(id); await refreshUser(); loadFeed(); loadHunters();
    }); };
    await loadComments(id);
    if (discussion) { $('#comment-form textarea').focus(); $('#comment-form').scrollIntoView({block:'nearest'}); }
  } catch (error) { toast(error.message,'error'); }
}
function setupDialog(dialog) {
  const close = dialog.querySelector('.close'); close.textContent = 'Đóng ×'; close.type = 'button'; close.setAttribute('aria-label','Quay lại');
  const top = document.createElement('div'); top.className = 'dialog-top'; close.before(top); top.append(close);
  if (dialog.id === 'profile-dialog') {
    top.prepend(dialog.querySelector('h2'));
    close.setAttribute('aria-label','Đóng hồ sơ');
  }
  close.onclick = () => dialog.close();
  let pressedOutside = false;
  const outside = event => { const rect = dialog.getBoundingClientRect(); return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom; };
  dialog.addEventListener('pointerdown', event => pressedOutside = event.target === dialog && outside(event));
  dialog.addEventListener('click', event => { if (pressedOutside && event.target === dialog && outside(event)) dialog.close(); pressedOutside = false; });
  dialog.addEventListener('close', () => dialog.querySelectorAll('form[data-locating="true"] .clear-location').forEach(button => button.click()));
  dialog.addEventListener('close', () => {
    if (dialog.contains(notification)) {
      const visible = !notification.hidden;
      if (typeof notification.hidePopover === 'function' && notification.matches(':popover-open')) notification.hidePopover();
      document.body.append(notification);
      if (visible && typeof notification.showPopover === 'function') notification.showPopover();
    }
  });
}
document.querySelectorAll('dialog').forEach(setupDialog);
$('#explore').onclick = () => { showMainPage('explore'); loadFeed(); };
$('#ranking').onclick = () => { showMainPage('ranking'); loadFeed(); window.scrollTo(0,0); };
$('#create').onclick = () => { if (requireLogin()) $('#create-dialog').showModal(); };
$('#compose-trigger').onclick = $('#compose-camera').onclick = () => $('#create').click();
$('#journey-action').onclick = () => $('#account').click();
$('#all-ranking').onclick = () => $('#ranking').click();
$('#load-more').onclick = () => busyMore();
async function busyMore() { $('#load-more').disabled = true; await loadFeed(true); $('#load-more').disabled = false; }
$('#account').onclick = () => { if (!user) { $('#auth-dialog').showModal(); return; } for (const key of ['display_name','bio','email','phone']) $('#profile-form').elements[key].value = user[key] || ''; $('#profile-dialog').showModal(); };
$('#logout').onclick = async () => { try { await api('/auth/logout', {method:'POST'}); token = ''; user = null; saveSessionToken(''); renderUser(); loadFeed(); $('#profile-dialog').close(); toast('Đã đăng xuất.'); } catch (error) { toast(error.message,'error'); } };
$('#profile-form').onsubmit = event => { event.preventDefault(); const form = event.currentTarget; busy(form, async () => { const body = Object.fromEntries(new FormData(form)); if (!body.email.trim() && !body.phone.trim()) throw new Error('Cần giữ email hoặc số điện thoại.'); user = await api('/me',{method:'PATCH',body}); renderUser(); $('#profile-dialog').close(); toast('Đã cập nhật hồ sơ.'); loadFeed(); loadHunters(); }); };
$('#auth-switch').onclick = () => { registerMode = !registerMode; $('#auth-title').textContent = registerMode ? 'Bắt đầu hành trình' : 'Chào mừng trở lại'; $('#auth-submit').textContent = registerMode ? 'Tạo tài khoản' : 'Đăng nhập'; $('#auth-switch').textContent = registerMode ? 'Đã có tài khoản? Đăng nhập' : 'Chưa có tài khoản? Đăng ký'; $('#auth-form [name=password]').autocomplete = registerMode ? 'new-password' : 'current-password'; contacts.hidden = !registerMode; contacts.querySelectorAll('input').forEach(input => input.disabled = !registerMode); if (registerMode) { loginInput.pattern = '[a-zA-Z0-9_]{3,30}'; loginInput.maxLength = 30; loginInput.placeholder = 'Không dấu, 3–30 ký tự'; } else { loginInput.removeAttribute('pattern'); loginInput.maxLength = 254; loginInput.placeholder = 'Tên đăng nhập, email hoặc số điện thoại'; } };
contacts.querySelectorAll('input').forEach(input => input.disabled = true);
$('#auth-form').onsubmit = event => { event.preventDefault(); const form = event.currentTarget; busy(form, async () => {
  const body=Object.fromEntries(new FormData(form));
  if (registerMode) {
    Object.assign(body,await consentPayload(form));
    if (!body.guardian_email && !String(body.email || '').trim() && !String(body.phone || '').trim()) throw new Error('Nhập email hoặc số điện thoại để đăng ký.');
  }
  const result=await api(`/auth/${registerMode ? 'register' : 'login'}`,{method:'POST',body});
  if (result.status==='pending_guardian') { formMessage(form,result.message,'success'); toast(result.message); return; }
  token=result.token; user=result.user; saveSessionToken(token); form.reset(); $('#auth-dialog').close(); renderUser(); loadFeed(); toast(`Xin chào ${user.display_name || user.username}!`);
}); };
$('#create-form').onsubmit = event => { event.preventDefault(); const form = event.currentTarget; busy(form, async () => { const f = new FormData(form), image = f.get('image'); if (!form.elements.content_rights_confirmed.checked) throw new Error('Cần xác nhận quyền sử dụng ảnh và trách nhiệm nội dung.'); if (image.size > 8 * 1024 * 1024) throw new Error('Ảnh tối đa 8 MB.'); if (Boolean(f.get('latitude')) !== Boolean(f.get('longitude'))) throw new Error('Cần nhập cả hai tọa độ.'); const upload = new FormData(); upload.append('file', image); upload.append('rights_confirmed','true'); const {image_url,scan} = await api('/uploads',{method:'POST',body:upload}); const body = {title:f.get('title'),description:f.get('description'),answer:f.get('answer'),aliases:String(f.get('aliases') || '').split(/\r?\n/).map(value => value.trim()).filter(Boolean),image_url,content_rights_confirmed:true}; for (const key of ['latitude','longitude']) if (f.get(key) !== '') body[key] = Number(f.get(key)); const created=await api('/cases',{method:'POST',body}); $('#create-dialog').close(); form.reset(); page = 'explore'; await loadFeed(); toast(created.moderation_status==='pending' ? (scan?.sensitive ? 'Ảnh có cảnh báo nội dung nhạy cảm. Bài đang chờ người kiểm duyệt, chưa công khai.' : 'Bài đã gửi, đang chờ kiểm duyệt trước khi công khai.') : 'Thử thách đã sẵn sàng. Để mọi người khám phá nào!'); }); };
refreshUser(); loadFeed(); loadHunters();
