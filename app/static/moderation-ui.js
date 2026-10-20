// Reports are private. Protected previews use Authorization, never URL tokens.
document.body.insertAdjacentHTML('beforeend',`<dialog id="report-dialog"><button class="close">×</button><h2>Báo cáo bài viết</h2><form id="report-form"><label>Lý do<select name="reason"><option value="sexual">Ảnh nhạy cảm / khiêu dâm</option><option value="privacy">Lộ khuôn mặt / biển số / thông tin riêng tư</option><option value="copyright">Vi phạm bản quyền</option><option value="violence">Bạo lực / nội dung nguy hiểm</option><option value="other">Lý do khác</option></select></label><label>Mô tả<textarea name="details" maxlength="1000"></textarea></label><p class="muted">Báo cáo chỉ gửi đến người kiểm duyệt; không công khai danh tính của bạn.</p><button type="submit" class="primary">Gửi báo cáo</button></form></dialog><dialog id="moderation-dialog" class="wide"><button class="close">×</button><h2>Kiểm duyệt nội dung</h2><p class="muted">Chỉ mở ảnh khi cần kiểm tra. Quét tự động có thể bỏ sót; kiểm tra cả mặt người, biển số và nội dung trước khi duyệt. Gỡ bài là ngừng công khai, chưa xóa dữ liệu lưu trữ.</p><button type="button" id="moderation-refresh" class="outline">Làm mới hàng chờ</button><div id="moderation-queue" aria-live="polite"></div><button type="button" id="moderation-next" class="outline" hidden>Trang tiếp theo</button><section id="account-moderation"><h3>Khóa / mở khóa tài khoản</h3><label>ID tài khoản<input id="moderation-user-id" type="number" min="1"></label><label>Lý do<input id="moderation-user-reason" minlength="5" maxlength="1000"></label><button type="button" id="moderation-suspend" class="outline">Khóa tài khoản</button><button type="button" id="moderation-unsuspend" class="outline">Mở khóa (quản trị viên)</button></section></dialog>`);
setupDialog($('#report-dialog'));setupDialog($('#moderation-dialog'));
let reportedCase=null,moderationOffset=0;
const previewURLs=new Set();
const reviewLabels={pending:'Chờ duyệt',approved:'Đã duyệt',removed:'Đã gỡ',scanned:'Đã quét',unavailable:'Chưa bật bộ quét',error:'Quét chưa hoàn tất',legacy:'Ảnh cũ chưa quét',manual_redaction:'Đã che thủ công',published:'Đã công khai'};
function clearPreviews(){for(const url of previewURLs)URL.revokeObjectURL(url);previewURLs.clear();}
$('#moderation-dialog').addEventListener('close',clearPreviews);
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-report-case]');
  if(!button)return;
  if(!user){$('#auth-dialog')?.showModal();return;}
  reportedCase=Number(button.dataset.reportCase);$('#report-form').reset();$('#report-dialog').showModal();
});
$('#report-form').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;busy(form,async()=>{
  const result=await api(`/cases/${reportedCase}/reports`,{method:'POST',body:Object.fromEntries(new FormData(form))});
  $('#report-dialog').close();toast(result.message);
});};
const staffButton=document.createElement('button');staffButton.type='button';staffButton.className='text-button';staffButton.textContent='Kiểm duyệt nội dung';staffButton.hidden=true;
$('.privacy-actions').append(staffButton);
window.renderStaffNav=()=>{staffButton.hidden=!user||!['moderator','admin'].includes(user.role);};
window.renderStaffNav();
staffButton.onclick=()=>{location.assign('/staff');};
$('#moderation-refresh').onclick=()=>{moderationOffset=0;loadModeration();};
$('#moderation-next').onclick=()=>{moderationOffset+=30;loadModeration();};
async function loadModeration(){
  const host=$('#moderation-queue');clearPreviews();host.textContent='Đang tải hàng chờ…';
  try{
    const result=await api('/moderation/queue?offset='+moderationOffset);
    host.innerHTML='';
    for(const image of result.images){
      const card=document.createElement('section');card.className='moderation-card';
      card.innerHTML=`<h3>Ảnh của tài khoản #${image.user_id}</h3><p>${esc(reviewLabels[image.status]||'Chưa xác định')} · ${esc(reviewLabels[image.scan.state]||'Cần kiểm tra')} · Đã che ${Number(image.scan.faces_blurred||0)} khuôn mặt</p><p class="moderation-warning">${esc((image.scan.warnings||[]).join(' '))}</p><button type="button" class="outline preview-image">Mở ảnh để kiểm tra</button><canvas class="review-canvas" hidden aria-label="Kéo để chọn vùng che mặt hoặc biển số"></canvas><p class="muted">Kéo trên ảnh để chọn vùng cần che. Mỗi lần lưu sẽ tạo bản ảnh mới chờ duyệt.</p><label>Lý do / ghi chú<input class="review-reason" maxlength="1000" placeholder="Ít nhất 5 ký tự"></label><div class="moderation-actions"><button type="button" class="outline redact-image">Che vùng đã chọn</button><button type="button" class="outline approve-image">Duyệt ảnh</button><button type="button" class="outline remove-image">Gỡ ảnh</button></div>`;
      host.append(card);
      const canvas=card.querySelector('canvas'),context=canvas.getContext('2d');let selected=null,bitmap=null,start=null;
      const point=e=>{const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))];};
      canvas.onpointerdown=e=>{start=point(e);canvas.setPointerCapture(e.pointerId);};
      canvas.onpointerup=e=>{if(!start)return;const end=point(e);selected=[Math.min(start[0],end[0]),Math.min(start[1],end[1]),Math.abs(end[0]-start[0]),Math.abs(end[1]-start[1])];start=null;context.drawImage(bitmap,0,0);context.strokeStyle='#d12c55';context.lineWidth=4;context.strokeRect(selected[0]*canvas.width,selected[1]*canvas.height,selected[2]*canvas.width,selected[3]*canvas.height);};
      card.querySelector('.preview-image').onclick=async event=>{
        const button=event.currentTarget;button.disabled=true;
        try{const response=await fetch(image.image_url,{headers:token?{Authorization:`Bearer ${token}`}:{'X-JinHunt-Staff':'1'},credentials:'same-origin'});if(!response.ok)throw Error('Không tải được ảnh riêng.');const url=URL.createObjectURL(await response.blob());previewURLs.add(url);bitmap=new Image();bitmap.onload=()=>{canvas.width=bitmap.width;canvas.height=bitmap.height;context.drawImage(bitmap,0,0);canvas.hidden=false;};bitmap.src=url;}catch(error){toast(error.message,'error');}finally{button.disabled=false;}
      };
      const action=async(button,kind)=>{button.disabled=true;try{const reason=card.querySelector('.review-reason').value.trim();if(reason.length<5)throw Error('Nhập lý do ít nhất 5 ký tự.');if(kind==='redact'){if(!selected||!selected[2]||!selected[3])throw Error('Hãy mở ảnh và kéo chọn vùng che.');await api('/moderation/images/redact',{method:'POST',body:{image_url:image.image_url,boxes:[selected],reason}});}else await api('/moderation/images/decision',{method:'POST',body:{image_url:image.image_url,action:kind,reason}});await loadModeration();toast('Đã lưu thao tác kiểm duyệt.');}catch(error){toast(error.message,'error');}finally{button.disabled=false;}};
      card.querySelector('.redact-image').onclick=e=>action(e.currentTarget,'redact');card.querySelector('.approve-image').onclick=e=>action(e.currentTarget,'approve');card.querySelector('.remove-image').onclick=e=>action(e.currentTarget,'remove');
    }
    const renderCase=(item,report)=>{
      const c=report?item.case:item,card=document.createElement('section');card.className='moderation-card';
      card.innerHTML=`<h3>${report?'Báo cáo #'+item.id:'Bài chờ duyệt'} · ${esc(c.title)}</h3><p>Bài #${c.id} · Tác giả #${c.creator_id} · ${esc(c.status)}</p><p>${esc(c.description)}</p>${report?`<p>Lý do: ${esc(item.reason)} · ${esc(item.details)}</p>`:''}<label>Lý do quyết định<input class="review-reason" maxlength="1000"></label><div class="moderation-actions"><button class="outline" data-decision="approve">${report?'Giữ bài / đóng báo cáo':'Duyệt bài'}</button><button class="outline" data-decision="remove">Gỡ bài</button></div>`;
      host.append(card);card.querySelectorAll('[data-decision]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await api(`/moderation/cases/${c.id}`,{method:'POST',body:{action:button.dataset.decision,reason:card.querySelector('.review-reason').value.trim()}});await loadModeration();loadFeed();toast('Đã xử lý bài viết.');}catch(error){toast(error.message,'error');}finally{button.disabled=false;}});
    };
    result.cases.forEach(c=>renderCase(c,false));result.reports.forEach(r=>renderCase(r,true));
    if(!host.children.length)host.textContent='Không còn nội dung trong hàng chờ này.';
    $('#moderation-next').hidden=result.cases.length<30&&result.reports.length<30&&result.images.length<30;
    $('#moderation-unsuspend').hidden=user?.role!=='admin';
  }catch(error){host.textContent='Chưa tải được hàng chờ. Bấm Làm mới để thử lại.';toast(error.message,'error');}
}
async function suspendAccount(suspended){
  const id=Number($('#moderation-user-id').value),reason=$('#moderation-user-reason').value.trim();
  if(!Number.isInteger(id)||id<1||reason.length<5){toast('Nhập ID tài khoản và lý do ít nhất 5 ký tự.','error');return;}
  if(!confirm(`${suspended?'Khóa':'Mở khóa'} tài khoản #${id}?`))return;
  try{await api(`/moderation/users/${id}/suspension`,{method:'POST',body:{suspended,reason}});toast('Đã cập nhật trạng thái tài khoản.');loadFeed();}catch(error){toast(error.message,'error');}
}
$('#moderation-suspend').onclick=()=>suspendAccount(true);$('#moderation-unsuspend').onclick=()=>suspendAccount(false);
