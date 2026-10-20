const staffLoginForm=document.querySelector('#staff-login-form');
staffLoginForm.onsubmit=async event=>{
  event.preventDefault();const button=staffLoginForm.querySelector('button'),message=document.querySelector('#staff-login-message');
  button.disabled=true;message.textContent='';
  try{
    const response=await fetch('/api/staff/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-JinHunt-Staff':'1'},body:JSON.stringify(Object.fromEntries(new FormData(staffLoginForm)))});
    const result=await response.json();
    if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'Kiểm tra thông tin và mã xác thực rồi thử lại.');
    staffLoginForm.reset();location.replace('/staff');
  }catch(error){message.textContent=error.message;staffLoginForm.elements.otp.value='';}
  finally{button.disabled=false;}
};
