// Apply before styles paint; keep this preference local to the device.
(()=>{
  const key='jinhunt-theme',modes=['system','light','dark'],media=matchMedia('(prefers-color-scheme: dark)');
  let mode='system';try{const saved=localStorage.getItem(key);if(modes.includes(saved))mode=saved;}catch{}
  function apply(){const dark=mode==='dark'||(mode==='system'&&media.matches);document.documentElement.dataset.theme=dark?'dark':'light';document.querySelector('meta[name="theme-color"]')?.setAttribute('content',dark?'#101b25':'#087d94');window.dispatchEvent(new CustomEvent('jinhunt-theme-change',{detail:{mode,dark}}));}
  window.jinhuntTheme={get:()=>mode,set:value=>{if(!modes.includes(value))return;mode=value;try{localStorage.setItem(key,value);}catch{}apply();}};
  if(media.addEventListener)media.addEventListener('change',apply);else media.addListener(apply);
  window.addEventListener('storage',event=>{if(event.key===key){mode=modes.includes(event.newValue)?event.newValue:'system';apply();}});
  apply();
})();
