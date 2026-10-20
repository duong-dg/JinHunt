// Email codes and registration proof stay in memory, never in URLs or localStorage.
const emailFlows=new Map();
function attachEmailFlow(form,registration){
  const email=form.elements.email,box=document.createElement('section');box.className='email-verification';
  box.innerHTML='<div class="email-verification-actions"><button type="button" class="outline email-send">Gửi mã xác minh email</button></div><div class="email-code-row" hidden><label>Mã xác minh 6 số<input type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" placeholder="6 chữ số trong email"></label><button type="button" class="outline email-confirm">Xác minh</button></div><p class="email-status" role="status" aria-live="polite"></p>';
  const emailLabel=email.closest('label');
  if(!registration){
    const field=document.createElement('div');field.className='profile-email-field';emailLabel.before(field);field.append(emailLabel,box);
  }else emailLabel.after(box);
  const edit=document.createElement('button');edit.type='button';edit.className='email-edit text-button';edit.textContent='Sửa';edit.hidden=true;
  const badge=document.createElement('span');badge.className='verified-badge';badge.textContent='✓ Đã xác minh';badge.hidden=true;
  if(!registration){const tools=document.createElement('div');tools.className='email-field-tools';tools.append(badge,edit);emailLabel.append(tools);}
  let editing=false;
  edit.onclick=()=>{editing=true;sync();email.focus();email.select();};
  const send=box.querySelector('.email-send'),confirm=box.querySelector('.email-confirm'),code=box.querySelector('input'),status=box.querySelector('.email-status'),row=box.querySelector('.email-code-row');
  const state={email:'',challenge:null,proof:null,ready:false,cooldown:0};emailFlows.set(form,state);
  const normalized=()=>email.value.trim().toLowerCase();
  const sync=(reset=false)=>{
    if(reset===true)editing=false;
    const current=normalized();
    if(current!==state.email){state.email=current;state.challenge=null;state.proof=null;state.ready=false;row.hidden=true;code.value='';}
    box.hidden=registration? !registerMode||email.disabled||!current:!user||user.guardian_managed||!current;
    const verified=!registration&&current===user?.email&&user?.email_verified;
    if(!registration){email.readOnly=Boolean(verified&&!editing);badge.hidden=!verified;edit.hidden=!verified||editing;box.hidden=box.hidden||Boolean(verified&&!editing);}
    if(verified){status.textContent='✓ Email đã xác minh';box.dataset.verified='true';send.hidden=true;row.hidden=true;}
    else{box.dataset.verified=state.ready?'true':'false';send.hidden=false;status.textContent=state.ready?'✓ Email đã xác minh, có thể hoàn tất đăng ký.':current?'Cần mã gửi đến hộp thư để xác minh email này.':'';}
  };
  email.addEventListener('input',sync);
  if(registration){$('#auth-switch').addEventListener('click',sync);form.addEventListener('change',sync);}
  const tick=()=>{const remaining=Math.ceil((state.cooldown-Date.now())/1000);send.disabled=remaining>0;send.textContent=remaining>0?`Gửi lại sau ${remaining}s`:'Gửi mã xác minh email';};
  send.onclick=async()=>{
    if(!email.validity.valid||!normalized()){status.textContent='Nhập địa chỉ email hợp lệ trước.';return;}
    const requested=normalized();send.disabled=true;
    try{
      const result=await api(registration?'/email-verification/request':'/me/email-verification/request',{method:'POST',body:{email:requested}});
      if(normalized()!==requested){status.textContent='Email đã thay đổi; hãy yêu cầu mã cho email đang nhập.';return;}
      state.email=requested;state.challenge=result.challenge_id;state.proof=null;state.ready=false;state.cooldown=Date.now()+result.retry_after*1000;
      row.hidden=false;code.disabled=false;code.value='';status.textContent=result.message+' Mã có hiệu lực 10 phút.';code.focus();tick();
    }catch(error){status.textContent=error.message;}
    finally{tick();}
  };
  confirm.onclick=async()=>{
    if(!state.challenge||state.email!==normalized()){status.textContent='Hãy yêu cầu mã cho email đang nhập.';return;}
    if(!/^[0-9]{6}$/.test(code.value.trim())){status.textContent='Nhập đủ 6 chữ số trong email.';return;}
    confirm.disabled=true;
    try{
      const expected=state.email;
      const result=await api(registration?'/email-verification/confirm':'/me/email-verification/confirm',{method:'POST',body:{challenge_id:state.challenge,code:code.value.trim()}});
      if(normalized()!==expected){status.textContent='Email đã thay đổi; hãy xác minh lại.';return;}
      if(registration){state.proof=result.verification_token;state.ready=true;status.textContent=result.message;row.hidden=true;box.dataset.verified='true';}
      else{user=result;renderUser();sync();toast('Đã xác minh và cập nhật email.');}
      code.value='';
    }catch(error){status.textContent=error.message;}
    finally{confirm.disabled=false;}
  };
  form.addEventListener('reset',()=>{state.email='';state.challenge=null;state.proof=null;state.ready=false;row.hidden=true;box.hidden=true;delete box.dataset.verified;code.value='';status.textContent='';if(registration)try{sessionStorage.removeItem('jinhunt-email-link-proof');}catch{}});
  setInterval(tick,1000);sync();return sync;
}
attachEmailFlow($('#auth-form'),true);
const refreshProfileEmail=attachEmailFlow($('#profile-form'),false);
window.renderEmailVerification=refreshProfileEmail;

function acceptLinkedEmail(result,restore=false){
  if(!result||typeof result.verification_token!=='string'||typeof result.email!=='string'||!Number.isFinite(result.expires_at)||result.expires_at*1000<=Date.now())return;
  const form=$('#auth-form'),state=emailFlows.get(form),box=form.querySelector('.email-verification');
  if(!restore&&(state.challenge!==result.challenge_id||form.elements.email.value.trim().toLowerCase()!==result.email))return;
  if(restore){
    if(!registerMode)$('#auth-switch').click();
    form.elements.email.value=result.email;
    form.elements.email.dispatchEvent(new Event('input',{bubbles:true}));
    $('#auth-dialog').showModal();
  }
  state.email=result.email;state.challenge=result.challenge_id;state.proof=result.verification_token;state.ready=true;
  box.hidden=false;box.dataset.verified='true';box.querySelector('.email-code-row').hidden=true;
  box.querySelector('.email-status').textContent='✓ Email đã xác minh bằng liên kết. Hoàn tất thông tin để tạo tài khoản.';
}
if(typeof BroadcastChannel==='function'){
  const emailLinkChannel=new BroadcastChannel('jinhunt-email-verification');
  emailLinkChannel.onmessage=event=>acceptLinkedEmail(event.data);
}
if(new URLSearchParams(location.search).get('register')==='verified'&&!token){
  try{acceptLinkedEmail(JSON.parse(sessionStorage.getItem('jinhunt-email-link-proof')),true);}catch{}
}
function registrationEmailProof(form){
  const email=form.elements.email;
  if(email.disabled||!email.value.trim())return null;
  const state=emailFlows.get(form);
  if(!state?.ready||state.email!==email.value.trim().toLowerCase()||!state.proof)throw Error('Hãy gửi mã và xác minh email trước khi tạo tài khoản.');
  return state.proof;
}
