const linkToken=new URLSearchParams(location.hash.slice(1)).get('token');
history.replaceState(null,'',location.pathname);
const verifyLinkButton=document.querySelector('#verify-email-link'),verifyLinkStatus=document.querySelector('#verify-email-status');
if(!linkToken){verifyLinkButton.disabled=true;verifyLinkStatus.textContent='Thiếu liên kết xác minh. Hãy mở đầy đủ liên kết trong thư hoặc dùng mã 6 số.';}
verifyLinkButton.onclick=async()=>{
  verifyLinkButton.disabled=true;
  try{
    const response=await fetch('/api/email-verification/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:linkToken}),cache:'no-store'});
    const result=await response.json();
    if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'Chưa xác minh được email.');
    try{sessionStorage.setItem('jinhunt-email-link-proof',JSON.stringify(result));}catch{}
    if(typeof BroadcastChannel==='function'){const channel=new BroadcastChannel('jinhunt-email-verification');channel.postMessage(result);channel.close();}
    verifyLinkStatus.textContent='Email đã xác minh. Quay lại tab đăng ký đang mở để hoàn tất, hoặc bấm Tiếp tục đăng ký bên dưới.';
    document.querySelector('#continue-registration').hidden=false;
  }catch(error){verifyLinkStatus.textContent=error.message;verifyLinkButton.disabled=false;}
};
