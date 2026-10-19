async function legalRequest(path,body) {
  let response;
  try { response=await fetch('/api'+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,cache:'no-store'}); }
  catch { throw new Error('Không kết nối được máy chủ. Hãy kiểm tra mạng và thử lại.'); }
  let data;try {data=await response.json();}catch{throw new Error('Máy chủ chưa xử lý được yêu cầu. Hãy thử lại sau.');}
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map(e=>e.msg?.replace(/^Value error, /,'')||'Thông tin chưa hợp lệ').join(' '):'Chưa xử lý được yêu cầu.');
  return data;
}
const supportForm=document.querySelector('#support-form');
if(supportForm){
  const kind=new URLSearchParams(location.search).get('kind');if([...supportForm.elements.kind.options].some(option=>option.value===kind))supportForm.elements.kind.value=kind;
  supportForm.onsubmit=async event=>{event.preventDefault();const button=supportForm.querySelector('button'),status=supportForm.querySelector('.form-status');button.disabled=true;status.classList.remove('error');status.textContent='Đang gửi yêu cầu…';try{const body=Object.fromEntries(new FormData(supportForm));body.contact_consent=supportForm.elements.contact_consent.checked;const result=await legalRequest('/legal/requests',body);supportForm.reset();status.textContent=result.message+'\nMã tham chiếu: '+result.reference;status.scrollIntoView({block:'nearest'});}catch(error){status.classList.add('error');status.textContent=error.message;}finally{button.disabled=false;}};
}
const guardianForm=document.querySelector('#guardian-form');
if(guardianForm){
  const raw=new URLSearchParams(location.hash.slice(1)).get('token');history.replaceState(null,'',location.pathname);
  let version=null;
  guardianForm.elements.guardian_name.closest('label').insertAdjacentHTML('afterend','<label>Bí danh công khai do người đại diện chọn<input name="display_name" required minlength="2" maxlength="80" placeholder="Không dùng tên thật hoặc thông tin nhận diện trẻ em"></label>');
  (async()=>{try{if(!raw)throw new Error('Thiếu liên kết xác nhận. Hãy mở đầy đủ liên kết trong email.');const preview=await legalRequest('/guardian/preview',{token:raw});version=preview.version;document.querySelector('#guardian-summary').textContent='Yêu cầu quản lý tài khoản @'+preview.username+'. Hãy đọc các chính sách, xác nhận tư cách đại diện và đặt mật khẩu riêng.';guardianForm.elements.display_name.value=preview.username;guardianForm.hidden=false;guardianForm.elements.child_assent_confirmed.required=preview.requires_child_assent;document.querySelector('#child-assent-row').hidden=!preview.requires_child_assent;}catch(error){document.querySelector('#guardian-summary').textContent=error.message+' Nếu liên kết hết hạn, dùng trang hỗ trợ để yêu cầu gửi lại.';}})();
  guardianForm.onsubmit=async event=>{event.preventDefault();const button=guardianForm.querySelector('button'),status=guardianForm.querySelector('.form-status');button.disabled=true;status.classList.remove('error');status.textContent='Đang xác nhận…';try{const body=Object.fromEntries(new FormData(guardianForm));for(const key of ['terms_accepted','privacy_accepted','authority_confirmed','child_assent_confirmed'])body[key]=guardianForm.elements[key].checked;body.token=raw;body.legal_version=version;const result=await legalRequest('/guardian/approve',body);guardianForm.reset();guardianForm.hidden=true;document.querySelector('#guardian-summary').textContent=result.message;}catch(error){status.classList.add('error');status.textContent=error.message;status.scrollIntoView({block:'nearest'});}finally{button.disabled=false;}};
}
