const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let token = sessionStorage.getItem('jinhunt-token') || '', user = null, registerMode = false, page = 'explore', toastTimer;
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 5000); }
async function api(path, options = {}) {
  const headers = {...(token ? {Authorization: `Bearer ${token}`} : {}), ...options.headers};
  if (options.body && !(options.body instanceof FormData)) { headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.body); }
  const response = await fetch(`/api${path}`, {...options, headers});
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) { if (response.status === 401) { token = ''; user = null; sessionStorage.removeItem('jinhunt-token'); renderUser(); } throw new Error(typeof data.detail === 'string' ? data.detail : 'Dữ liệu chưa hợp lệ. Vui lòng kiểm tra các ô nhập.'); }
  return data;
}
function renderUser() { $('#account').textContent = user ? `${user.username} · Đăng xuất` : 'Đăng nhập'; $('#profile').textContent = user ? `Level ${user.level} · ${user.xp} XP · ${200 - user.xp % 200} XP tới level tiếp theo` : 'Khám phá theo cách của bạn ↗'; }
async function refreshUser() { if (token) { try { user = await api('/me'); } catch {} } renderUser(); }
function requireLogin() { if (user) return true; $('#auth-dialog').showModal(); return false; }
async function busy(form, task) { const button = form.querySelector('[type="submit"]'); button.disabled = true; try { await task(); } catch (error) { toast(error.message); } finally { button.disabled = false; } }
async function loadFeed() {
  $('#explore').classList.toggle('active', page === 'explore'); $('#ranking').classList.toggle('active', page === 'ranking');
  $('#section-title').textContent = page === 'explore' ? 'Những nơi chờ bạn tìm ra' : 'Những nhà khám phá hàng đầu';
  $('#feed').innerHTML = '<div class="empty">Đang tải hành trình…</div>';
  try {
    if (page === 'ranking') { const rows = await api('/leaderboard'); $('#feed').innerHTML = rows.length ? rows.map((u,i) => `<div class="leader"><span>${String(i+1).padStart(2,'0')}</span><strong>${esc(u.username)}</strong><span class="score">Level ${u.level} · ${u.xp} XP</span></div>`).join('') : '<div class="empty">Bảng xếp hạng đang chờ nhà khám phá đầu tiên.</div>'; return; }
    const rows = await api('/cases');
    $('#feed').innerHTML = rows.length ? rows.map(c => `<button class="card" data-case="${c.id}"><img src="${esc(c.image_url)}" alt="Ảnh thử thách ${esc(c.title)}" loading="lazy"><div class="card-body"><span class="badge">ĐỊA ĐIỂM BÍ ẨN · +${c.reward_xp} XP</span><h3>${esc(c.title)}</h3><p>${esc(c.description.slice(0,100)) || 'Bạn nhận ra địa điểm này chứ?'}</p><div class="card-meta"><span>↗ ${esc(c.creator)}</span><span>${c.solves} người giải được</span></div></div></button>`).join('') : '<div class="empty"><p class="eyebrow">TẤM ẢNH ĐẦU TIÊN. HÀNH TRÌNH ĐẦU TIÊN.</p><h3>Một địa điểm thú vị đang chờ bạn chia sẻ</h3><p>Chụp một góc quen, đặt đáp án bí mật<br>và để cộng đồng tìm ra câu chuyện phía sau.</p><button class="primary" id="empty-create">＋ Tạo thử thách đầu tiên</button></div>';
    document.querySelectorAll('[data-case]').forEach(b => b.onclick = () => openCase(Number(b.dataset.case)));
    if ($('#empty-create')) $('#empty-create').onclick = () => $('#create').click();
  } catch (error) { $('#feed').innerHTML = '<div class="empty">Không tải được dữ liệu. <button id="retry">Thử lại</button></div>'; $('#retry').onclick = loadFeed; toast(error.message); }
}
async function loadComments(id) { const rows = await api(`/cases/${id}/comments`); $('#comments').innerHTML = rows.length ? rows.map(c => `<div class="comment ${c.is_hidden ? 'hidden-comment' : ''}"><strong>${esc(c.username)}</strong><p>${esc(c.content)}</p></div>`).join('') : '<p class="muted">Chưa có trao đổi. Hãy bắt đầu với một gợi ý!</p>'; }
async function openCase(id) {
  try {
    const c = await api(`/cases/${id}`);
    $('#detail').innerHTML = `<p class="eyebrow">THỬ THÁCH #${c.id} · +${c.reward_xp} XP</p><h2>${esc(c.title)}</h2><p class="muted">Chia sẻ bởi ${esc(c.creator)} · ${c.solves} người đoán đúng</p><img class="detail-image" src="${esc(c.image_url)}" alt="Ảnh địa điểm bí ẩn"><p>${esc(c.description)}</p><form id="guess-form"><label>Địa điểm này tên gì?<input name="answer" maxlength="200" placeholder="Nhập đáp án bí mật của bạn…"></label>${c.has_coordinates ? '<details><summary>Hoặc dự đoán bằng tọa độ</summary><div class="row"><label>Vĩ độ<input name="latitude" type="number" step="any" min="-90" max="90"></label><label>Kinh độ<input name="longitude" type="number" step="any" min="-180" max="180"></label></div></details>' : ''}<button class="primary" type="submit">Gửi dự đoán ↗</button><p id="guess-result" role="status" class="muted">Đáp án chỉ gửi riêng đến hệ thống.</p></form><hr><h3>Trao đổi & gợi ý</h3><div id="comments"></div><form id="comment-form"><label>Bình luận<textarea name="content" required maxlength="1000" placeholder="Chia sẻ suy nghĩ của bạn…"></textarea></label><button class="primary" type="submit">Gửi bình luận</button><p class="muted">Bình luận chứa tên đáp án sẽ tự động được che.</p></form>`;
    if (!$('#detail-dialog').open) $('#detail-dialog').showModal();
    $('#guess-form').onsubmit = event => { event.preventDefault(); if (!user) { toast('Đăng nhập trước khi dự đoán.'); return; } const form = event.currentTarget; busy(form, async () => { const f = new FormData(form), body = {answer: f.get('answer')}; for (const key of ['latitude','longitude']) if (f.get(key) !== null && f.get(key) !== '') body[key] = Number(f.get(key)); if (!body.answer.trim() && !(body.latitude !== undefined && body.longitude !== undefined)) throw new Error('Nhập tên địa điểm hoặc đủ hai tọa độ.'); const result = await api(`/cases/${id}/guesses`, {method:'POST',body}); $('#guess-result').textContent = ({correct:`Chính xác! Bạn nhận +${result.reward_xp} XP.`, incorrect:'Chưa đúng rồi. Hãy xem kỹ ảnh và thử lại!', already_solved:'Bạn đã giải được thử thách này rồi.'})[result.status]; await refreshUser(); loadFeed(); }); };
    $('#comment-form').onsubmit = event => { event.preventDefault(); if (!user) { toast('Đăng nhập trước khi bình luận.'); return; } const form = event.currentTarget; busy(form, async () => { const result = await api(`/cases/${id}/comments`, {method:'POST',body:{content:new FormData(form).get('content')}}); form.reset(); await loadComments(id); if (result.is_hidden) toast('Bình luận có chứa đáp án nên đã được che.'); }); };
    await loadComments(id);
  } catch (error) { toast(error.message); }
}
document.querySelectorAll('.close').forEach(button => button.onclick = () => button.closest('dialog').close());
$('#explore').onclick = () => { page = 'explore'; loadFeed(); };
$('#ranking').onclick = () => { page = 'ranking'; loadFeed(); };
$('#create').onclick = () => { if (requireLogin()) $('#create-dialog').showModal(); };
$('#account').onclick = async () => { if (!user) { $('#auth-dialog').showModal(); return; } try { await api('/auth/logout', {method:'POST'}); token = ''; user = null; sessionStorage.removeItem('jinhunt-token'); renderUser(); toast('Đã đăng xuất.'); } catch (error) { toast(error.message); } };
$('#auth-switch').onclick = () => { registerMode = !registerMode; $('#auth-title').textContent = registerMode ? 'Bắt đầu hành trình' : 'Chào mừng trở lại'; $('#auth-submit').textContent = registerMode ? 'Tạo tài khoản' : 'Đăng nhập'; $('#auth-switch').textContent = registerMode ? 'Đã có tài khoản? Đăng nhập' : 'Chưa có tài khoản? Đăng ký'; $('#auth-form [name=password]').autocomplete = registerMode ? 'new-password' : 'current-password'; };
$('#auth-form').onsubmit = event => { event.preventDefault(); const form = event.currentTarget; busy(form, async () => { const result = await api(`/auth/${registerMode ? 'register' : 'login'}`,{method:'POST',body:Object.fromEntries(new FormData(form))}); token = result.token; user = result.user; sessionStorage.setItem('jinhunt-token',token); renderUser(); form.reset(); $('#auth-dialog').close(); toast(`Xin chào ${user.username}!`); }); };
$('#create-form').onsubmit = event => { event.preventDefault(); const form = event.currentTarget; busy(form, async () => { const f = new FormData(form), image = f.get('image'); if (image.size > 8 * 1024 * 1024) throw new Error('Ảnh tối đa 8 MB.'); if (Boolean(f.get('latitude')) !== Boolean(f.get('longitude'))) throw new Error('Cần nhập cả hai tọa độ.'); const upload = new FormData(); upload.append('file', image); const {image_url} = await api('/uploads',{method:'POST',body:upload}); const body = {title:f.get('title'),description:f.get('description'),answer:f.get('answer'),image_url}; for (const key of ['latitude','longitude']) if (f.get(key) !== '') body[key] = Number(f.get(key)); await api('/cases',{method:'POST',body}); $('#create-dialog').close(); form.reset(); page = 'explore'; await loadFeed(); toast('Thử thách đã sẵn sàng. Để mọi người khám phá nào!'); }); };
refreshUser(); loadFeed();
