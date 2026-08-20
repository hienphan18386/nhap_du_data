(function(){
  var n=document.getElementById('__mxcap');
  if(n){ n.textContent='[]'; return 'rearmed'; }
  n=document.createElement('div'); n.id='__mxcap'; n.style.display='none';
  n.textContent='[]';
  document.body.appendChild(n);
  var s=document.createElement('script');
  s.textContent="(function(){"
   +"if(window.__mxTapped) return; window.__mxTapped=1;"
   +"var mem=[];"
   +"var node=function(){var n=document.getElementById('__mxcap');"
   +"if(!n){n=document.createElement('div');n.id='__mxcap';n.style.display='none';"
   +"(document.body||document.documentElement).appendChild(n);}return n;};"
   +"var keep=function(m,u,b){try{"
   +"if(String(m||'GET').toUpperCase()==='GET')return;"
   +"mem.push({m:m,u:u,b:(typeof b==='string'?b.slice(0,400000):null)});"
   +"node().textContent=JSON.stringify(mem);}catch(e){}};"
   +"var O=XMLHttpRequest.prototype.open,S=XMLHttpRequest.prototype.send;"
   +"XMLHttpRequest.prototype.open=function(m,u){this.__m=m;this.__u=u;return O.apply(this,arguments);};"
   +"XMLHttpRequest.prototype.send=function(b){keep(this.__m,this.__u,b);return S.apply(this,arguments);};"
   +"var F=window.fetch;window.fetch=function(a,b){try{"
   +"var u=(typeof a==='string')?a:(a&&a.url)||'';var m=(b&&b.method)||'GET';"
   +"keep(m,u,b&&typeof b.body==='string'?b.body:null);}catch(e){}"
   +"return F.apply(this,arguments);};})();";
  document.documentElement.appendChild(s); s.remove();
  return 'tapped';
})()
