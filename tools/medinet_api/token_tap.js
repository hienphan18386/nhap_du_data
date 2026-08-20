
(function(){
  if (document.getElementById('__mxtok')) return 'already';
  var out = document.createElement('div');
  out.id = '__mxtok';
  out.style.display = 'none';
  document.body.appendChild(out);
  var s = document.createElement('script');
  s.textContent = "(function(){var S=XMLHttpRequest.prototype.setRequestHeader;" +
    "XMLHttpRequest.prototype.setRequestHeader=function(k,v){try{" +
    "if(String(k).toLowerCase()==='authorization'){var n=document.getElementById('__mxtok');" +
    "if(n)n.textContent=String(v);}}catch(e){}return S.apply(this,arguments);};" +
    "var F=window.fetch;window.fetch=function(a,b){try{var h=b&&b.headers;" +
    "var v=h?(h.Authorization||h.authorization||(h.get&&h.get('Authorization'))):null;" +
    "if(v){var n=document.getElementById('__mxtok');if(n)n.textContent=String(v);}}catch(e){}" +
    "return F.apply(this,arguments);};})();";
  document.documentElement.appendChild(s);
  s.remove();
  return 'tapped';
})()
