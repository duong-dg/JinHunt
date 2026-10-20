const $=s=>document.querySelector(s);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let user=null,token='';
function toast(message,kind='success'){const box=$('#staff-notice');box.textContent=message;box.hidden=false;box.dataset.kind=kind;}
function requireLogin(){return !!user;}
function loadFeed(){}
function setupDialog(dialog){const button=dialog.querySelector('.close');button.type='button';button.setAttribute('aria-label','Đóng');button.onclick=()=>dialog.close();}
async function busy(form,work){const button=form.querySelector('[type=submit]');button.disabled=true;try{await work();}catch(error){toast(error.message,'error');}finally{button.disabled=false;}}
async function api(path,options={}){
  const headers={'X-JinHunt-Staff':'1',...options.headers};
  if(options.body){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  const response=await fetch('/api'+path,{...options,headers,credentials:'same-origin'});
  const result=response.status===204?null:await response.json();
  if(response.status===401){location.replace('/staff/login');throw Error('Phiên quản trị đã hết hạn.');}
  if(!response.ok)throw Error(typeof result?.detail==='string'?result.detail:'Chưa thực hiện được yêu cầu.');
  return result;
}
document.addEventListener('DOMContentLoaded',async()=>{
  try{
    user=await api('/staff/session');$('#staff-name').textContent=user.display_name||user.username;
    $('#staff-session-status').remove();window.renderStaffNav?.();
    const panel=$('#moderation-dialog');panel.querySelector('.close').hidden=true;
    $('#staff-content').append(panel);panel.show();await loadModeration();
  }catch(error){if($('#staff-session-status'))$('#staff-session-status').textContent=error.message;}
});
$('#staff-signout').onclick=async()=>{try{await api('/staff/logout',{method:'POST'});location.replace('/staff/login');}catch(error){toast(error.message,'error');}};
