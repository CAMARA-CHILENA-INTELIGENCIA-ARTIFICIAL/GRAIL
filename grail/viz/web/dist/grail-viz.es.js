var Jn = { value: () => {
} };
function Xt() {
  for (var t = 0, e = arguments.length, n = {}, r; t < e; ++t) {
    if (!(r = arguments[t] + "") || r in n || /[\s.]/.test(r)) throw new Error("illegal type: " + r);
    n[r] = [];
  }
  return new Zt(n);
}
function Zt(t) {
  this._ = t;
}
function jn(t, e) {
  return t.trim().split(/^|\s+/).map(function(n) {
    var r = "", i = n.indexOf(".");
    if (i >= 0 && (r = n.slice(i + 1), n = n.slice(0, i)), n && !e.hasOwnProperty(n)) throw new Error("unknown type: " + n);
    return { type: n, name: r };
  });
}
Zt.prototype = Xt.prototype = {
  constructor: Zt,
  on: function(t, e) {
    var n = this._, r = jn(t + "", n), i, o = -1, s = r.length;
    if (arguments.length < 2) {
      for (; ++o < s; ) if ((i = (t = r[o]).type) && (i = tr(n[i], t.name))) return i;
      return;
    }
    if (e != null && typeof e != "function") throw new Error("invalid callback: " + e);
    for (; ++o < s; )
      if (i = (t = r[o]).type) n[i] = Pe(n[i], t.name, e);
      else if (e == null) for (i in n) n[i] = Pe(n[i], t.name, null);
    return this;
  },
  copy: function() {
    var t = {}, e = this._;
    for (var n in e) t[n] = e[n].slice();
    return new Zt(t);
  },
  call: function(t, e) {
    if ((i = arguments.length - 2) > 0) for (var n = new Array(i), r = 0, i, o; r < i; ++r) n[r] = arguments[r + 2];
    if (!this._.hasOwnProperty(t)) throw new Error("unknown type: " + t);
    for (o = this._[t], r = 0, i = o.length; r < i; ++r) o[r].value.apply(e, n);
  },
  apply: function(t, e, n) {
    if (!this._.hasOwnProperty(t)) throw new Error("unknown type: " + t);
    for (var r = this._[t], i = 0, o = r.length; i < o; ++i) r[i].value.apply(e, n);
  }
};
function tr(t, e) {
  for (var n = 0, r = t.length, i; n < r; ++n)
    if ((i = t[n]).name === e)
      return i.value;
}
function Pe(t, e, n) {
  for (var r = 0, i = t.length; r < i; ++r)
    if (t[r].name === e) {
      t[r] = Jn, t = t.slice(0, r).concat(t.slice(r + 1));
      break;
    }
  return n != null && t.push({ name: e, value: n }), t;
}
var xe = "http://www.w3.org/1999/xhtml";
const Xe = {
  svg: "http://www.w3.org/2000/svg",
  xhtml: xe,
  xlink: "http://www.w3.org/1999/xlink",
  xml: "http://www.w3.org/XML/1998/namespace",
  xmlns: "http://www.w3.org/2000/xmlns/"
};
function ae(t) {
  var e = t += "", n = e.indexOf(":");
  return n >= 0 && (e = t.slice(0, n)) !== "xmlns" && (t = t.slice(n + 1)), Xe.hasOwnProperty(e) ? { space: Xe[e], local: t } : t;
}
function er(t) {
  return function() {
    var e = this.ownerDocument, n = this.namespaceURI;
    return n === xe && e.documentElement.namespaceURI === xe ? e.createElement(t) : e.createElementNS(n, t);
  };
}
function nr(t) {
  return function() {
    return this.ownerDocument.createElementNS(t.space, t.local);
  };
}
function wn(t) {
  var e = ae(t);
  return (e.local ? nr : er)(e);
}
function rr() {
}
function Se(t) {
  return t == null ? rr : function() {
    return this.querySelector(t);
  };
}
function ir(t) {
  typeof t != "function" && (t = Se(t));
  for (var e = this._groups, n = e.length, r = new Array(n), i = 0; i < n; ++i)
    for (var o = e[i], s = o.length, u = r[i] = new Array(s), c, a, l = 0; l < s; ++l)
      (c = o[l]) && (a = t.call(c, c.__data__, l, o)) && ("__data__" in c && (a.__data__ = c.__data__), u[l] = a);
  return new it(r, this._parents);
}
function or(t) {
  return t == null ? [] : Array.isArray(t) ? t : Array.from(t);
}
function sr() {
  return [];
}
function bn(t) {
  return t == null ? sr : function() {
    return this.querySelectorAll(t);
  };
}
function ar(t) {
  return function() {
    return or(t.apply(this, arguments));
  };
}
function ur(t) {
  typeof t == "function" ? t = ar(t) : t = bn(t);
  for (var e = this._groups, n = e.length, r = [], i = [], o = 0; o < n; ++o)
    for (var s = e[o], u = s.length, c, a = 0; a < u; ++a)
      (c = s[a]) && (r.push(t.call(c, c.__data__, a, s)), i.push(c));
  return new it(r, i);
}
function kn(t) {
  return function() {
    return this.matches(t);
  };
}
function En(t) {
  return function(e) {
    return e.matches(t);
  };
}
var cr = Array.prototype.find;
function lr(t) {
  return function() {
    return cr.call(this.children, t);
  };
}
function fr() {
  return this.firstElementChild;
}
function hr(t) {
  return this.select(t == null ? fr : lr(typeof t == "function" ? t : En(t)));
}
var gr = Array.prototype.filter;
function dr() {
  return Array.from(this.children);
}
function yr(t) {
  return function() {
    return gr.call(this.children, t);
  };
}
function pr(t) {
  return this.selectAll(t == null ? dr : yr(typeof t == "function" ? t : En(t)));
}
function mr(t) {
  typeof t != "function" && (t = kn(t));
  for (var e = this._groups, n = e.length, r = new Array(n), i = 0; i < n; ++i)
    for (var o = e[i], s = o.length, u = r[i] = [], c, a = 0; a < s; ++a)
      (c = o[a]) && t.call(c, c.__data__, a, o) && u.push(c);
  return new it(r, this._parents);
}
function Mn(t) {
  return new Array(t.length);
}
function vr() {
  return new it(this._enter || this._groups.map(Mn), this._parents);
}
function ee(t, e) {
  this.ownerDocument = t.ownerDocument, this.namespaceURI = t.namespaceURI, this._next = null, this._parent = t, this.__data__ = e;
}
ee.prototype = {
  constructor: ee,
  appendChild: function(t) {
    return this._parent.insertBefore(t, this._next);
  },
  insertBefore: function(t, e) {
    return this._parent.insertBefore(t, e);
  },
  querySelector: function(t) {
    return this._parent.querySelector(t);
  },
  querySelectorAll: function(t) {
    return this._parent.querySelectorAll(t);
  }
};
function _r(t) {
  return function() {
    return t;
  };
}
function xr(t, e, n, r, i, o) {
  for (var s = 0, u, c = e.length, a = o.length; s < a; ++s)
    (u = e[s]) ? (u.__data__ = o[s], r[s] = u) : n[s] = new ee(t, o[s]);
  for (; s < c; ++s)
    (u = e[s]) && (i[s] = u);
}
function wr(t, e, n, r, i, o, s) {
  var u, c, a = /* @__PURE__ */ new Map(), l = e.length, v = o.length, h = new Array(l), d;
  for (u = 0; u < l; ++u)
    (c = e[u]) && (h[u] = d = s.call(c, c.__data__, u, e) + "", a.has(d) ? i[u] = c : a.set(d, c));
  for (u = 0; u < v; ++u)
    d = s.call(t, o[u], u, o) + "", (c = a.get(d)) ? (r[u] = c, c.__data__ = o[u], a.delete(d)) : n[u] = new ee(t, o[u]);
  for (u = 0; u < l; ++u)
    (c = e[u]) && a.get(h[u]) === c && (i[u] = c);
}
function br(t) {
  return t.__data__;
}
function kr(t, e) {
  if (!arguments.length) return Array.from(this, br);
  var n = e ? wr : xr, r = this._parents, i = this._groups;
  typeof t != "function" && (t = _r(t));
  for (var o = i.length, s = new Array(o), u = new Array(o), c = new Array(o), a = 0; a < o; ++a) {
    var l = r[a], v = i[a], h = v.length, d = Er(t.call(l, l && l.__data__, a, r)), k = d.length, _ = u[a] = new Array(k), f = s[a] = new Array(k), m = c[a] = new Array(h);
    n(l, v, _, f, m, d, e);
    for (var M = 0, C = 0, p, T; M < k; ++M)
      if (p = _[M]) {
        for (M >= C && (C = M + 1); !(T = f[C]) && ++C < k; ) ;
        p._next = T || null;
      }
  }
  return s = new it(s, r), s._enter = u, s._exit = c, s;
}
function Er(t) {
  return typeof t == "object" && "length" in t ? t : Array.from(t);
}
function Mr() {
  return new it(this._exit || this._groups.map(Mn), this._parents);
}
function Nr(t, e, n) {
  var r = this.enter(), i = this, o = this.exit();
  return typeof t == "function" ? (r = t(r), r && (r = r.selection())) : r = r.append(t + ""), e != null && (i = e(i), i && (i = i.selection())), n == null ? o.remove() : n(o), r && i ? r.merge(i).order() : i;
}
function $r(t) {
  for (var e = t.selection ? t.selection() : t, n = this._groups, r = e._groups, i = n.length, o = r.length, s = Math.min(i, o), u = new Array(i), c = 0; c < s; ++c)
    for (var a = n[c], l = r[c], v = a.length, h = u[c] = new Array(v), d, k = 0; k < v; ++k)
      (d = a[k] || l[k]) && (h[k] = d);
  for (; c < i; ++c)
    u[c] = n[c];
  return new it(u, this._parents);
}
function Sr() {
  for (var t = this._groups, e = -1, n = t.length; ++e < n; )
    for (var r = t[e], i = r.length - 1, o = r[i], s; --i >= 0; )
      (s = r[i]) && (o && s.compareDocumentPosition(o) ^ 4 && o.parentNode.insertBefore(s, o), o = s);
  return this;
}
function Ar(t) {
  t || (t = Tr);
  function e(v, h) {
    return v && h ? t(v.__data__, h.__data__) : !v - !h;
  }
  for (var n = this._groups, r = n.length, i = new Array(r), o = 0; o < r; ++o) {
    for (var s = n[o], u = s.length, c = i[o] = new Array(u), a, l = 0; l < u; ++l)
      (a = s[l]) && (c[l] = a);
    c.sort(e);
  }
  return new it(i, this._parents).order();
}
function Tr(t, e) {
  return t < e ? -1 : t > e ? 1 : t >= e ? 0 : NaN;
}
function Cr() {
  var t = arguments[0];
  return arguments[0] = this, t.apply(null, arguments), this;
}
function zr() {
  return Array.from(this);
}
function Dr() {
  for (var t = this._groups, e = 0, n = t.length; e < n; ++e)
    for (var r = t[e], i = 0, o = r.length; i < o; ++i) {
      var s = r[i];
      if (s) return s;
    }
  return null;
}
function Rr() {
  let t = 0;
  for (const e of this) ++t;
  return t;
}
function Ir() {
  return !this.node();
}
function Lr(t) {
  for (var e = this._groups, n = 0, r = e.length; n < r; ++n)
    for (var i = e[n], o = 0, s = i.length, u; o < s; ++o)
      (u = i[o]) && t.call(u, u.__data__, o, i);
  return this;
}
function Fr(t) {
  return function() {
    this.removeAttribute(t);
  };
}
function Or(t) {
  return function() {
    this.removeAttributeNS(t.space, t.local);
  };
}
function Kr(t, e) {
  return function() {
    this.setAttribute(t, e);
  };
}
function Hr(t, e) {
  return function() {
    this.setAttributeNS(t.space, t.local, e);
  };
}
function Pr(t, e) {
  return function() {
    var n = e.apply(this, arguments);
    n == null ? this.removeAttribute(t) : this.setAttribute(t, n);
  };
}
function Xr(t, e) {
  return function() {
    var n = e.apply(this, arguments);
    n == null ? this.removeAttributeNS(t.space, t.local) : this.setAttributeNS(t.space, t.local, n);
  };
}
function Yr(t, e) {
  var n = ae(t);
  if (arguments.length < 2) {
    var r = this.node();
    return n.local ? r.getAttributeNS(n.space, n.local) : r.getAttribute(n);
  }
  return this.each((e == null ? n.local ? Or : Fr : typeof e == "function" ? n.local ? Xr : Pr : n.local ? Hr : Kr)(n, e));
}
function Nn(t) {
  return t.ownerDocument && t.ownerDocument.defaultView || t.document && t || t.defaultView;
}
function qr(t) {
  return function() {
    this.style.removeProperty(t);
  };
}
function Br(t, e, n) {
  return function() {
    this.style.setProperty(t, e, n);
  };
}
function Vr(t, e, n) {
  return function() {
    var r = e.apply(this, arguments);
    r == null ? this.style.removeProperty(t) : this.style.setProperty(t, r, n);
  };
}
function Gr(t, e, n) {
  return arguments.length > 1 ? this.each((e == null ? qr : typeof e == "function" ? Vr : Br)(t, e, n ?? "")) : Tt(this.node(), t);
}
function Tt(t, e) {
  return t.style.getPropertyValue(e) || Nn(t).getComputedStyle(t, null).getPropertyValue(e);
}
function Ur(t) {
  return function() {
    delete this[t];
  };
}
function Wr(t, e) {
  return function() {
    this[t] = e;
  };
}
function Qr(t, e) {
  return function() {
    var n = e.apply(this, arguments);
    n == null ? delete this[t] : this[t] = n;
  };
}
function Zr(t, e) {
  return arguments.length > 1 ? this.each((e == null ? Ur : typeof e == "function" ? Qr : Wr)(t, e)) : this.node()[t];
}
function $n(t) {
  return t.trim().split(/^|\s+/);
}
function Ae(t) {
  return t.classList || new Sn(t);
}
function Sn(t) {
  this._node = t, this._names = $n(t.getAttribute("class") || "");
}
Sn.prototype = {
  add: function(t) {
    var e = this._names.indexOf(t);
    e < 0 && (this._names.push(t), this._node.setAttribute("class", this._names.join(" ")));
  },
  remove: function(t) {
    var e = this._names.indexOf(t);
    e >= 0 && (this._names.splice(e, 1), this._node.setAttribute("class", this._names.join(" ")));
  },
  contains: function(t) {
    return this._names.indexOf(t) >= 0;
  }
};
function An(t, e) {
  for (var n = Ae(t), r = -1, i = e.length; ++r < i; ) n.add(e[r]);
}
function Tn(t, e) {
  for (var n = Ae(t), r = -1, i = e.length; ++r < i; ) n.remove(e[r]);
}
function Jr(t) {
  return function() {
    An(this, t);
  };
}
function jr(t) {
  return function() {
    Tn(this, t);
  };
}
function ti(t, e) {
  return function() {
    (e.apply(this, arguments) ? An : Tn)(this, t);
  };
}
function ei(t, e) {
  var n = $n(t + "");
  if (arguments.length < 2) {
    for (var r = Ae(this.node()), i = -1, o = n.length; ++i < o; ) if (!r.contains(n[i])) return !1;
    return !0;
  }
  return this.each((typeof e == "function" ? ti : e ? Jr : jr)(n, e));
}
function ni() {
  this.textContent = "";
}
function ri(t) {
  return function() {
    this.textContent = t;
  };
}
function ii(t) {
  return function() {
    var e = t.apply(this, arguments);
    this.textContent = e ?? "";
  };
}
function oi(t) {
  return arguments.length ? this.each(t == null ? ni : (typeof t == "function" ? ii : ri)(t)) : this.node().textContent;
}
function si() {
  this.innerHTML = "";
}
function ai(t) {
  return function() {
    this.innerHTML = t;
  };
}
function ui(t) {
  return function() {
    var e = t.apply(this, arguments);
    this.innerHTML = e ?? "";
  };
}
function ci(t) {
  return arguments.length ? this.each(t == null ? si : (typeof t == "function" ? ui : ai)(t)) : this.node().innerHTML;
}
function li() {
  this.nextSibling && this.parentNode.appendChild(this);
}
function fi() {
  return this.each(li);
}
function hi() {
  this.previousSibling && this.parentNode.insertBefore(this, this.parentNode.firstChild);
}
function gi() {
  return this.each(hi);
}
function di(t) {
  var e = typeof t == "function" ? t : wn(t);
  return this.select(function() {
    return this.appendChild(e.apply(this, arguments));
  });
}
function yi() {
  return null;
}
function pi(t, e) {
  var n = typeof t == "function" ? t : wn(t), r = e == null ? yi : typeof e == "function" ? e : Se(e);
  return this.select(function() {
    return this.insertBefore(n.apply(this, arguments), r.apply(this, arguments) || null);
  });
}
function mi() {
  var t = this.parentNode;
  t && t.removeChild(this);
}
function vi() {
  return this.each(mi);
}
function _i() {
  var t = this.cloneNode(!1), e = this.parentNode;
  return e ? e.insertBefore(t, this.nextSibling) : t;
}
function xi() {
  var t = this.cloneNode(!0), e = this.parentNode;
  return e ? e.insertBefore(t, this.nextSibling) : t;
}
function wi(t) {
  return this.select(t ? xi : _i);
}
function bi(t) {
  return arguments.length ? this.property("__data__", t) : this.node().__data__;
}
function ki(t) {
  return function(e) {
    t.call(this, e, this.__data__);
  };
}
function Ei(t) {
  return t.trim().split(/^|\s+/).map(function(e) {
    var n = "", r = e.indexOf(".");
    return r >= 0 && (n = e.slice(r + 1), e = e.slice(0, r)), { type: e, name: n };
  });
}
function Mi(t) {
  return function() {
    var e = this.__on;
    if (e) {
      for (var n = 0, r = -1, i = e.length, o; n < i; ++n)
        o = e[n], (!t.type || o.type === t.type) && o.name === t.name ? this.removeEventListener(o.type, o.listener, o.options) : e[++r] = o;
      ++r ? e.length = r : delete this.__on;
    }
  };
}
function Ni(t, e, n) {
  return function() {
    var r = this.__on, i, o = ki(e);
    if (r) {
      for (var s = 0, u = r.length; s < u; ++s)
        if ((i = r[s]).type === t.type && i.name === t.name) {
          this.removeEventListener(i.type, i.listener, i.options), this.addEventListener(i.type, i.listener = o, i.options = n), i.value = e;
          return;
        }
    }
    this.addEventListener(t.type, o, n), i = { type: t.type, name: t.name, value: e, listener: o, options: n }, r ? r.push(i) : this.__on = [i];
  };
}
function $i(t, e, n) {
  var r = Ei(t + ""), i, o = r.length, s;
  if (arguments.length < 2) {
    var u = this.node().__on;
    if (u) {
      for (var c = 0, a = u.length, l; c < a; ++c)
        for (i = 0, l = u[c]; i < o; ++i)
          if ((s = r[i]).type === l.type && s.name === l.name)
            return l.value;
    }
    return;
  }
  for (u = e ? Ni : Mi, i = 0; i < o; ++i) this.each(u(r[i], e, n));
  return this;
}
function Cn(t, e, n) {
  var r = Nn(t), i = r.CustomEvent;
  typeof i == "function" ? i = new i(e, n) : (i = r.document.createEvent("Event"), n ? (i.initEvent(e, n.bubbles, n.cancelable), i.detail = n.detail) : i.initEvent(e, !1, !1)), t.dispatchEvent(i);
}
function Si(t, e) {
  return function() {
    return Cn(this, t, e);
  };
}
function Ai(t, e) {
  return function() {
    return Cn(this, t, e.apply(this, arguments));
  };
}
function Ti(t, e) {
  return this.each((typeof e == "function" ? Ai : Si)(t, e));
}
function* Ci() {
  for (var t = this._groups, e = 0, n = t.length; e < n; ++e)
    for (var r = t[e], i = 0, o = r.length, s; i < o; ++i)
      (s = r[i]) && (yield s);
}
var zn = [null];
function it(t, e) {
  this._groups = t, this._parents = e;
}
function Yt() {
  return new it([[document.documentElement]], zn);
}
function zi() {
  return this;
}
it.prototype = Yt.prototype = {
  constructor: it,
  select: ir,
  selectAll: ur,
  selectChild: hr,
  selectChildren: pr,
  filter: mr,
  data: kr,
  enter: vr,
  exit: Mr,
  join: Nr,
  merge: $r,
  selection: zi,
  order: Sr,
  sort: Ar,
  call: Cr,
  nodes: zr,
  node: Dr,
  size: Rr,
  empty: Ir,
  each: Lr,
  attr: Yr,
  style: Gr,
  property: Zr,
  classed: ei,
  text: oi,
  html: ci,
  raise: fi,
  lower: gi,
  append: di,
  insert: pi,
  remove: vi,
  clone: wi,
  datum: bi,
  on: $i,
  dispatch: Ti,
  [Symbol.iterator]: Ci
};
function rt(t) {
  return typeof t == "string" ? new it([[document.querySelector(t)]], [document.documentElement]) : new it([[t]], zn);
}
function Di(t) {
  let e;
  for (; e = t.sourceEvent; ) t = e;
  return t;
}
function mt(t, e) {
  if (t = Di(t), e === void 0 && (e = t.currentTarget), e) {
    var n = e.ownerSVGElement || e;
    if (n.createSVGPoint) {
      var r = n.createSVGPoint();
      return r.x = t.clientX, r.y = t.clientY, r = r.matrixTransform(e.getScreenCTM().inverse()), [r.x, r.y];
    }
    if (e.getBoundingClientRect) {
      var i = e.getBoundingClientRect();
      return [t.clientX - i.left - e.clientLeft, t.clientY - i.top - e.clientTop];
    }
  }
  return [t.pageX, t.pageY];
}
const Ri = { passive: !1 }, Ft = { capture: !0, passive: !1 };
function fe(t) {
  t.stopImmediatePropagation();
}
function St(t) {
  t.preventDefault(), t.stopImmediatePropagation();
}
function Dn(t) {
  var e = t.document.documentElement, n = rt(t).on("dragstart.drag", St, Ft);
  "onselectstart" in e ? n.on("selectstart.drag", St, Ft) : (e.__noselect = e.style.MozUserSelect, e.style.MozUserSelect = "none");
}
function Rn(t, e) {
  var n = t.document.documentElement, r = rt(t).on("dragstart.drag", null);
  e && (r.on("click.drag", St, Ft), setTimeout(function() {
    r.on("click.drag", null);
  }, 0)), "onselectstart" in n ? r.on("selectstart.drag", null) : (n.style.MozUserSelect = n.__noselect, delete n.__noselect);
}
const Vt = (t) => () => t;
function we(t, {
  sourceEvent: e,
  subject: n,
  target: r,
  identifier: i,
  active: o,
  x: s,
  y: u,
  dx: c,
  dy: a,
  dispatch: l
}) {
  Object.defineProperties(this, {
    type: { value: t, enumerable: !0, configurable: !0 },
    sourceEvent: { value: e, enumerable: !0, configurable: !0 },
    subject: { value: n, enumerable: !0, configurable: !0 },
    target: { value: r, enumerable: !0, configurable: !0 },
    identifier: { value: i, enumerable: !0, configurable: !0 },
    active: { value: o, enumerable: !0, configurable: !0 },
    x: { value: s, enumerable: !0, configurable: !0 },
    y: { value: u, enumerable: !0, configurable: !0 },
    dx: { value: c, enumerable: !0, configurable: !0 },
    dy: { value: a, enumerable: !0, configurable: !0 },
    _: { value: l }
  });
}
we.prototype.on = function() {
  var t = this._.on.apply(this._, arguments);
  return t === this._ ? this : t;
};
function Ii(t) {
  return !t.ctrlKey && !t.button;
}
function Li() {
  return this.parentNode;
}
function Fi(t, e) {
  return e ?? { x: t.x, y: t.y };
}
function Oi() {
  return navigator.maxTouchPoints || "ontouchstart" in this;
}
function Ki() {
  var t = Ii, e = Li, n = Fi, r = Oi, i = {}, o = Xt("start", "drag", "end"), s = 0, u, c, a, l, v = 0;
  function h(p) {
    p.on("mousedown.drag", d).filter(r).on("touchstart.drag", f).on("touchmove.drag", m, Ri).on("touchend.drag touchcancel.drag", M).style("touch-action", "none").style("-webkit-tap-highlight-color", "rgba(0,0,0,0)");
  }
  function d(p, T) {
    if (!(l || !t.call(this, p, T))) {
      var x = C(this, e.call(this, p, T), p, T, "mouse");
      x && (rt(p.view).on("mousemove.drag", k, Ft).on("mouseup.drag", _, Ft), Dn(p.view), fe(p), a = !1, u = p.clientX, c = p.clientY, x("start", p));
    }
  }
  function k(p) {
    if (St(p), !a) {
      var T = p.clientX - u, x = p.clientY - c;
      a = T * T + x * x > v;
    }
    i.mouse("drag", p);
  }
  function _(p) {
    rt(p.view).on("mousemove.drag mouseup.drag", null), Rn(p.view, a), St(p), i.mouse("end", p);
  }
  function f(p, T) {
    if (t.call(this, p, T)) {
      var x = p.changedTouches, $ = e.call(this, p, T), D = x.length, K, H;
      for (K = 0; K < D; ++K)
        (H = C(this, $, p, T, x[K].identifier, x[K])) && (fe(p), H("start", p, x[K]));
    }
  }
  function m(p) {
    var T = p.changedTouches, x = T.length, $, D;
    for ($ = 0; $ < x; ++$)
      (D = i[T[$].identifier]) && (St(p), D("drag", p, T[$]));
  }
  function M(p) {
    var T = p.changedTouches, x = T.length, $, D;
    for (l && clearTimeout(l), l = setTimeout(function() {
      l = null;
    }, 500), $ = 0; $ < x; ++$)
      (D = i[T[$].identifier]) && (fe(p), D("end", p, T[$]));
  }
  function C(p, T, x, $, D, K) {
    var H = o.copy(), q = mt(K || x, T), Q, W, y;
    if ((y = n.call(p, new we("beforestart", {
      sourceEvent: x,
      target: h,
      identifier: D,
      active: s,
      x: q[0],
      y: q[1],
      dx: 0,
      dy: 0,
      dispatch: H
    }), $)) != null)
      return Q = y.x - q[0] || 0, W = y.y - q[1] || 0, function S(w, z, R) {
        var I = q, F;
        switch (w) {
          case "start":
            i[D] = S, F = s++;
            break;
          case "end":
            delete i[D], --s;
          // falls through
          case "drag":
            q = mt(R || z, T), F = s;
            break;
        }
        H.call(
          w,
          p,
          new we(w, {
            sourceEvent: z,
            subject: y,
            target: h,
            identifier: D,
            active: F,
            x: q[0] + Q,
            y: q[1] + W,
            dx: q[0] - I[0],
            dy: q[1] - I[1],
            dispatch: H
          }),
          $
        );
      };
  }
  return h.filter = function(p) {
    return arguments.length ? (t = typeof p == "function" ? p : Vt(!!p), h) : t;
  }, h.container = function(p) {
    return arguments.length ? (e = typeof p == "function" ? p : Vt(p), h) : e;
  }, h.subject = function(p) {
    return arguments.length ? (n = typeof p == "function" ? p : Vt(p), h) : n;
  }, h.touchable = function(p) {
    return arguments.length ? (r = typeof p == "function" ? p : Vt(!!p), h) : r;
  }, h.on = function() {
    var p = o.on.apply(o, arguments);
    return p === o ? h : p;
  }, h.clickDistance = function(p) {
    return arguments.length ? (v = (p = +p) * p, h) : Math.sqrt(v);
  }, h;
}
function Te(t, e, n) {
  t.prototype = e.prototype = n, n.constructor = t;
}
function In(t, e) {
  var n = Object.create(t.prototype);
  for (var r in e) n[r] = e[r];
  return n;
}
function qt() {
}
var Ot = 0.7, ne = 1 / Ot, At = "\\s*([+-]?\\d+)\\s*", Kt = "\\s*([+-]?(?:\\d*\\.)?\\d+(?:[eE][+-]?\\d+)?)\\s*", dt = "\\s*([+-]?(?:\\d*\\.)?\\d+(?:[eE][+-]?\\d+)?)%\\s*", Hi = /^#([0-9a-f]{3,8})$/, Pi = new RegExp(`^rgb\\(${At},${At},${At}\\)$`), Xi = new RegExp(`^rgb\\(${dt},${dt},${dt}\\)$`), Yi = new RegExp(`^rgba\\(${At},${At},${At},${Kt}\\)$`), qi = new RegExp(`^rgba\\(${dt},${dt},${dt},${Kt}\\)$`), Bi = new RegExp(`^hsl\\(${Kt},${dt},${dt}\\)$`), Vi = new RegExp(`^hsla\\(${Kt},${dt},${dt},${Kt}\\)$`), Ye = {
  aliceblue: 15792383,
  antiquewhite: 16444375,
  aqua: 65535,
  aquamarine: 8388564,
  azure: 15794175,
  beige: 16119260,
  bisque: 16770244,
  black: 0,
  blanchedalmond: 16772045,
  blue: 255,
  blueviolet: 9055202,
  brown: 10824234,
  burlywood: 14596231,
  cadetblue: 6266528,
  chartreuse: 8388352,
  chocolate: 13789470,
  coral: 16744272,
  cornflowerblue: 6591981,
  cornsilk: 16775388,
  crimson: 14423100,
  cyan: 65535,
  darkblue: 139,
  darkcyan: 35723,
  darkgoldenrod: 12092939,
  darkgray: 11119017,
  darkgreen: 25600,
  darkgrey: 11119017,
  darkkhaki: 12433259,
  darkmagenta: 9109643,
  darkolivegreen: 5597999,
  darkorange: 16747520,
  darkorchid: 10040012,
  darkred: 9109504,
  darksalmon: 15308410,
  darkseagreen: 9419919,
  darkslateblue: 4734347,
  darkslategray: 3100495,
  darkslategrey: 3100495,
  darkturquoise: 52945,
  darkviolet: 9699539,
  deeppink: 16716947,
  deepskyblue: 49151,
  dimgray: 6908265,
  dimgrey: 6908265,
  dodgerblue: 2003199,
  firebrick: 11674146,
  floralwhite: 16775920,
  forestgreen: 2263842,
  fuchsia: 16711935,
  gainsboro: 14474460,
  ghostwhite: 16316671,
  gold: 16766720,
  goldenrod: 14329120,
  gray: 8421504,
  green: 32768,
  greenyellow: 11403055,
  grey: 8421504,
  honeydew: 15794160,
  hotpink: 16738740,
  indianred: 13458524,
  indigo: 4915330,
  ivory: 16777200,
  khaki: 15787660,
  lavender: 15132410,
  lavenderblush: 16773365,
  lawngreen: 8190976,
  lemonchiffon: 16775885,
  lightblue: 11393254,
  lightcoral: 15761536,
  lightcyan: 14745599,
  lightgoldenrodyellow: 16448210,
  lightgray: 13882323,
  lightgreen: 9498256,
  lightgrey: 13882323,
  lightpink: 16758465,
  lightsalmon: 16752762,
  lightseagreen: 2142890,
  lightskyblue: 8900346,
  lightslategray: 7833753,
  lightslategrey: 7833753,
  lightsteelblue: 11584734,
  lightyellow: 16777184,
  lime: 65280,
  limegreen: 3329330,
  linen: 16445670,
  magenta: 16711935,
  maroon: 8388608,
  mediumaquamarine: 6737322,
  mediumblue: 205,
  mediumorchid: 12211667,
  mediumpurple: 9662683,
  mediumseagreen: 3978097,
  mediumslateblue: 8087790,
  mediumspringgreen: 64154,
  mediumturquoise: 4772300,
  mediumvioletred: 13047173,
  midnightblue: 1644912,
  mintcream: 16121850,
  mistyrose: 16770273,
  moccasin: 16770229,
  navajowhite: 16768685,
  navy: 128,
  oldlace: 16643558,
  olive: 8421376,
  olivedrab: 7048739,
  orange: 16753920,
  orangered: 16729344,
  orchid: 14315734,
  palegoldenrod: 15657130,
  palegreen: 10025880,
  paleturquoise: 11529966,
  palevioletred: 14381203,
  papayawhip: 16773077,
  peachpuff: 16767673,
  peru: 13468991,
  pink: 16761035,
  plum: 14524637,
  powderblue: 11591910,
  purple: 8388736,
  rebeccapurple: 6697881,
  red: 16711680,
  rosybrown: 12357519,
  royalblue: 4286945,
  saddlebrown: 9127187,
  salmon: 16416882,
  sandybrown: 16032864,
  seagreen: 3050327,
  seashell: 16774638,
  sienna: 10506797,
  silver: 12632256,
  skyblue: 8900331,
  slateblue: 6970061,
  slategray: 7372944,
  slategrey: 7372944,
  snow: 16775930,
  springgreen: 65407,
  steelblue: 4620980,
  tan: 13808780,
  teal: 32896,
  thistle: 14204888,
  tomato: 16737095,
  turquoise: 4251856,
  violet: 15631086,
  wheat: 16113331,
  white: 16777215,
  whitesmoke: 16119285,
  yellow: 16776960,
  yellowgreen: 10145074
};
Te(qt, Ht, {
  copy(t) {
    return Object.assign(new this.constructor(), this, t);
  },
  displayable() {
    return this.rgb().displayable();
  },
  hex: qe,
  // Deprecated! Use color.formatHex.
  formatHex: qe,
  formatHex8: Gi,
  formatHsl: Ui,
  formatRgb: Be,
  toString: Be
});
function qe() {
  return this.rgb().formatHex();
}
function Gi() {
  return this.rgb().formatHex8();
}
function Ui() {
  return Ln(this).formatHsl();
}
function Be() {
  return this.rgb().formatRgb();
}
function Ht(t) {
  var e, n;
  return t = (t + "").trim().toLowerCase(), (e = Hi.exec(t)) ? (n = e[1].length, e = parseInt(e[1], 16), n === 6 ? Ve(e) : n === 3 ? new et(e >> 8 & 15 | e >> 4 & 240, e >> 4 & 15 | e & 240, (e & 15) << 4 | e & 15, 1) : n === 8 ? Gt(e >> 24 & 255, e >> 16 & 255, e >> 8 & 255, (e & 255) / 255) : n === 4 ? Gt(e >> 12 & 15 | e >> 8 & 240, e >> 8 & 15 | e >> 4 & 240, e >> 4 & 15 | e & 240, ((e & 15) << 4 | e & 15) / 255) : null) : (e = Pi.exec(t)) ? new et(e[1], e[2], e[3], 1) : (e = Xi.exec(t)) ? new et(e[1] * 255 / 100, e[2] * 255 / 100, e[3] * 255 / 100, 1) : (e = Yi.exec(t)) ? Gt(e[1], e[2], e[3], e[4]) : (e = qi.exec(t)) ? Gt(e[1] * 255 / 100, e[2] * 255 / 100, e[3] * 255 / 100, e[4]) : (e = Bi.exec(t)) ? We(e[1], e[2] / 100, e[3] / 100, 1) : (e = Vi.exec(t)) ? We(e[1], e[2] / 100, e[3] / 100, e[4]) : Ye.hasOwnProperty(t) ? Ve(Ye[t]) : t === "transparent" ? new et(NaN, NaN, NaN, 0) : null;
}
function Ve(t) {
  return new et(t >> 16 & 255, t >> 8 & 255, t & 255, 1);
}
function Gt(t, e, n, r) {
  return r <= 0 && (t = e = n = NaN), new et(t, e, n, r);
}
function Wi(t) {
  return t instanceof qt || (t = Ht(t)), t ? (t = t.rgb(), new et(t.r, t.g, t.b, t.opacity)) : new et();
}
function be(t, e, n, r) {
  return arguments.length === 1 ? Wi(t) : new et(t, e, n, r ?? 1);
}
function et(t, e, n, r) {
  this.r = +t, this.g = +e, this.b = +n, this.opacity = +r;
}
Te(et, be, In(qt, {
  brighter(t) {
    return t = t == null ? ne : Math.pow(ne, t), new et(this.r * t, this.g * t, this.b * t, this.opacity);
  },
  darker(t) {
    return t = t == null ? Ot : Math.pow(Ot, t), new et(this.r * t, this.g * t, this.b * t, this.opacity);
  },
  rgb() {
    return this;
  },
  clamp() {
    return new et(Mt(this.r), Mt(this.g), Mt(this.b), re(this.opacity));
  },
  displayable() {
    return -0.5 <= this.r && this.r < 255.5 && -0.5 <= this.g && this.g < 255.5 && -0.5 <= this.b && this.b < 255.5 && 0 <= this.opacity && this.opacity <= 1;
  },
  hex: Ge,
  // Deprecated! Use color.formatHex.
  formatHex: Ge,
  formatHex8: Qi,
  formatRgb: Ue,
  toString: Ue
}));
function Ge() {
  return `#${Et(this.r)}${Et(this.g)}${Et(this.b)}`;
}
function Qi() {
  return `#${Et(this.r)}${Et(this.g)}${Et(this.b)}${Et((isNaN(this.opacity) ? 1 : this.opacity) * 255)}`;
}
function Ue() {
  const t = re(this.opacity);
  return `${t === 1 ? "rgb(" : "rgba("}${Mt(this.r)}, ${Mt(this.g)}, ${Mt(this.b)}${t === 1 ? ")" : `, ${t})`}`;
}
function re(t) {
  return isNaN(t) ? 1 : Math.max(0, Math.min(1, t));
}
function Mt(t) {
  return Math.max(0, Math.min(255, Math.round(t) || 0));
}
function Et(t) {
  return t = Mt(t), (t < 16 ? "0" : "") + t.toString(16);
}
function We(t, e, n, r) {
  return r <= 0 ? t = e = n = NaN : n <= 0 || n >= 1 ? t = e = NaN : e <= 0 && (t = NaN), new lt(t, e, n, r);
}
function Ln(t) {
  if (t instanceof lt) return new lt(t.h, t.s, t.l, t.opacity);
  if (t instanceof qt || (t = Ht(t)), !t) return new lt();
  if (t instanceof lt) return t;
  t = t.rgb();
  var e = t.r / 255, n = t.g / 255, r = t.b / 255, i = Math.min(e, n, r), o = Math.max(e, n, r), s = NaN, u = o - i, c = (o + i) / 2;
  return u ? (e === o ? s = (n - r) / u + (n < r) * 6 : n === o ? s = (r - e) / u + 2 : s = (e - n) / u + 4, u /= c < 0.5 ? o + i : 2 - o - i, s *= 60) : u = c > 0 && c < 1 ? 0 : s, new lt(s, u, c, t.opacity);
}
function Zi(t, e, n, r) {
  return arguments.length === 1 ? Ln(t) : new lt(t, e, n, r ?? 1);
}
function lt(t, e, n, r) {
  this.h = +t, this.s = +e, this.l = +n, this.opacity = +r;
}
Te(lt, Zi, In(qt, {
  brighter(t) {
    return t = t == null ? ne : Math.pow(ne, t), new lt(this.h, this.s, this.l * t, this.opacity);
  },
  darker(t) {
    return t = t == null ? Ot : Math.pow(Ot, t), new lt(this.h, this.s, this.l * t, this.opacity);
  },
  rgb() {
    var t = this.h % 360 + (this.h < 0) * 360, e = isNaN(t) || isNaN(this.s) ? 0 : this.s, n = this.l, r = n + (n < 0.5 ? n : 1 - n) * e, i = 2 * n - r;
    return new et(
      he(t >= 240 ? t - 240 : t + 120, i, r),
      he(t, i, r),
      he(t < 120 ? t + 240 : t - 120, i, r),
      this.opacity
    );
  },
  clamp() {
    return new lt(Qe(this.h), Ut(this.s), Ut(this.l), re(this.opacity));
  },
  displayable() {
    return (0 <= this.s && this.s <= 1 || isNaN(this.s)) && 0 <= this.l && this.l <= 1 && 0 <= this.opacity && this.opacity <= 1;
  },
  formatHsl() {
    const t = re(this.opacity);
    return `${t === 1 ? "hsl(" : "hsla("}${Qe(this.h)}, ${Ut(this.s) * 100}%, ${Ut(this.l) * 100}%${t === 1 ? ")" : `, ${t})`}`;
  }
}));
function Qe(t) {
  return t = (t || 0) % 360, t < 0 ? t + 360 : t;
}
function Ut(t) {
  return Math.max(0, Math.min(1, t || 0));
}
function he(t, e, n) {
  return (t < 60 ? e + (n - e) * t / 60 : t < 180 ? n : t < 240 ? e + (n - e) * (240 - t) / 60 : e) * 255;
}
const Fn = (t) => () => t;
function Ji(t, e) {
  return function(n) {
    return t + n * e;
  };
}
function ji(t, e, n) {
  return t = Math.pow(t, n), e = Math.pow(e, n) - t, n = 1 / n, function(r) {
    return Math.pow(t + r * e, n);
  };
}
function to(t) {
  return (t = +t) == 1 ? On : function(e, n) {
    return n - e ? ji(e, n, t) : Fn(isNaN(e) ? n : e);
  };
}
function On(t, e) {
  var n = e - t;
  return n ? Ji(t, n) : Fn(isNaN(t) ? e : t);
}
const Ze = (function t(e) {
  var n = to(e);
  function r(i, o) {
    var s = n((i = be(i)).r, (o = be(o)).r), u = n(i.g, o.g), c = n(i.b, o.b), a = On(i.opacity, o.opacity);
    return function(l) {
      return i.r = s(l), i.g = u(l), i.b = c(l), i.opacity = a(l), i + "";
    };
  }
  return r.gamma = t, r;
})(1);
function xt(t, e) {
  return t = +t, e = +e, function(n) {
    return t * (1 - n) + e * n;
  };
}
var ke = /[-+]?(?:\d+\.?\d*|\.?\d+)(?:[eE][-+]?\d+)?/g, ge = new RegExp(ke.source, "g");
function eo(t) {
  return function() {
    return t;
  };
}
function no(t) {
  return function(e) {
    return t(e) + "";
  };
}
function ro(t, e) {
  var n = ke.lastIndex = ge.lastIndex = 0, r, i, o, s = -1, u = [], c = [];
  for (t = t + "", e = e + ""; (r = ke.exec(t)) && (i = ge.exec(e)); )
    (o = i.index) > n && (o = e.slice(n, o), u[s] ? u[s] += o : u[++s] = o), (r = r[0]) === (i = i[0]) ? u[s] ? u[s] += i : u[++s] = i : (u[++s] = null, c.push({ i: s, x: xt(r, i) })), n = ge.lastIndex;
  return n < e.length && (o = e.slice(n), u[s] ? u[s] += o : u[++s] = o), u.length < 2 ? c[0] ? no(c[0].x) : eo(e) : (e = c.length, function(a) {
    for (var l = 0, v; l < e; ++l) u[(v = c[l]).i] = v.x(a);
    return u.join("");
  });
}
var Je = 180 / Math.PI, Ee = {
  translateX: 0,
  translateY: 0,
  rotate: 0,
  skewX: 0,
  scaleX: 1,
  scaleY: 1
};
function Kn(t, e, n, r, i, o) {
  var s, u, c;
  return (s = Math.sqrt(t * t + e * e)) && (t /= s, e /= s), (c = t * n + e * r) && (n -= t * c, r -= e * c), (u = Math.sqrt(n * n + r * r)) && (n /= u, r /= u, c /= u), t * r < e * n && (t = -t, e = -e, c = -c, s = -s), {
    translateX: i,
    translateY: o,
    rotate: Math.atan2(e, t) * Je,
    skewX: Math.atan(c) * Je,
    scaleX: s,
    scaleY: u
  };
}
var Wt;
function io(t) {
  const e = new (typeof DOMMatrix == "function" ? DOMMatrix : WebKitCSSMatrix)(t + "");
  return e.isIdentity ? Ee : Kn(e.a, e.b, e.c, e.d, e.e, e.f);
}
function oo(t) {
  return t == null || (Wt || (Wt = document.createElementNS("http://www.w3.org/2000/svg", "g")), Wt.setAttribute("transform", t), !(t = Wt.transform.baseVal.consolidate())) ? Ee : (t = t.matrix, Kn(t.a, t.b, t.c, t.d, t.e, t.f));
}
function Hn(t, e, n, r) {
  function i(a) {
    return a.length ? a.pop() + " " : "";
  }
  function o(a, l, v, h, d, k) {
    if (a !== v || l !== h) {
      var _ = d.push("translate(", null, e, null, n);
      k.push({ i: _ - 4, x: xt(a, v) }, { i: _ - 2, x: xt(l, h) });
    } else (v || h) && d.push("translate(" + v + e + h + n);
  }
  function s(a, l, v, h) {
    a !== l ? (a - l > 180 ? l += 360 : l - a > 180 && (a += 360), h.push({ i: v.push(i(v) + "rotate(", null, r) - 2, x: xt(a, l) })) : l && v.push(i(v) + "rotate(" + l + r);
  }
  function u(a, l, v, h) {
    a !== l ? h.push({ i: v.push(i(v) + "skewX(", null, r) - 2, x: xt(a, l) }) : l && v.push(i(v) + "skewX(" + l + r);
  }
  function c(a, l, v, h, d, k) {
    if (a !== v || l !== h) {
      var _ = d.push(i(d) + "scale(", null, ",", null, ")");
      k.push({ i: _ - 4, x: xt(a, v) }, { i: _ - 2, x: xt(l, h) });
    } else (v !== 1 || h !== 1) && d.push(i(d) + "scale(" + v + "," + h + ")");
  }
  return function(a, l) {
    var v = [], h = [];
    return a = t(a), l = t(l), o(a.translateX, a.translateY, l.translateX, l.translateY, v, h), s(a.rotate, l.rotate, v, h), u(a.skewX, l.skewX, v, h), c(a.scaleX, a.scaleY, l.scaleX, l.scaleY, v, h), a = l = null, function(d) {
      for (var k = -1, _ = h.length, f; ++k < _; ) v[(f = h[k]).i] = f.x(d);
      return v.join("");
    };
  };
}
var so = Hn(io, "px, ", "px)", "deg)"), ao = Hn(oo, ", ", ")", ")"), uo = 1e-12;
function je(t) {
  return ((t = Math.exp(t)) + 1 / t) / 2;
}
function co(t) {
  return ((t = Math.exp(t)) - 1 / t) / 2;
}
function lo(t) {
  return ((t = Math.exp(2 * t)) - 1) / (t + 1);
}
const fo = (function t(e, n, r) {
  function i(o, s) {
    var u = o[0], c = o[1], a = o[2], l = s[0], v = s[1], h = s[2], d = l - u, k = v - c, _ = d * d + k * k, f, m;
    if (_ < uo)
      m = Math.log(h / a) / e, f = function($) {
        return [
          u + $ * d,
          c + $ * k,
          a * Math.exp(e * $ * m)
        ];
      };
    else {
      var M = Math.sqrt(_), C = (h * h - a * a + r * _) / (2 * a * n * M), p = (h * h - a * a - r * _) / (2 * h * n * M), T = Math.log(Math.sqrt(C * C + 1) - C), x = Math.log(Math.sqrt(p * p + 1) - p);
      m = (x - T) / e, f = function($) {
        var D = $ * m, K = je(T), H = a / (n * M) * (K * lo(e * D + T) - co(T));
        return [
          u + H * d,
          c + H * k,
          a * K / je(e * D + T)
        ];
      };
    }
    return f.duration = m * 1e3 * e / Math.SQRT2, f;
  }
  return i.rho = function(o) {
    var s = Math.max(1e-3, +o), u = s * s, c = u * u;
    return t(s, u, c);
  }, i;
})(Math.SQRT2, 2, 4);
var Ct = 0, Rt = 0, zt = 0, Pn = 1e3, ie, It, oe = 0, Nt = 0, ue = 0, Pt = typeof performance == "object" && performance.now ? performance : Date, Xn = typeof window == "object" && window.requestAnimationFrame ? window.requestAnimationFrame.bind(window) : function(t) {
  setTimeout(t, 17);
};
function Ce() {
  return Nt || (Xn(ho), Nt = Pt.now() + ue);
}
function ho() {
  Nt = 0;
}
function se() {
  this._call = this._time = this._next = null;
}
se.prototype = ze.prototype = {
  constructor: se,
  restart: function(t, e, n) {
    if (typeof t != "function") throw new TypeError("callback is not a function");
    n = (n == null ? Ce() : +n) + (e == null ? 0 : +e), !this._next && It !== this && (It ? It._next = this : ie = this, It = this), this._call = t, this._time = n, Me();
  },
  stop: function() {
    this._call && (this._call = null, this._time = 1 / 0, Me());
  }
};
function ze(t, e, n) {
  var r = new se();
  return r.restart(t, e, n), r;
}
function go() {
  Ce(), ++Ct;
  for (var t = ie, e; t; )
    (e = Nt - t._time) >= 0 && t._call.call(void 0, e), t = t._next;
  --Ct;
}
function tn() {
  Nt = (oe = Pt.now()) + ue, Ct = Rt = 0;
  try {
    go();
  } finally {
    Ct = 0, po(), Nt = 0;
  }
}
function yo() {
  var t = Pt.now(), e = t - oe;
  e > Pn && (ue -= e, oe = t);
}
function po() {
  for (var t, e = ie, n, r = 1 / 0; e; )
    e._call ? (r > e._time && (r = e._time), t = e, e = e._next) : (n = e._next, e._next = null, e = t ? t._next = n : ie = n);
  It = t, Me(r);
}
function Me(t) {
  if (!Ct) {
    Rt && (Rt = clearTimeout(Rt));
    var e = t - Nt;
    e > 24 ? (t < 1 / 0 && (Rt = setTimeout(tn, t - Pt.now() - ue)), zt && (zt = clearInterval(zt))) : (zt || (oe = Pt.now(), zt = setInterval(yo, Pn)), Ct = 1, Xn(tn));
  }
}
function en(t, e, n) {
  var r = new se();
  return e = e == null ? 0 : +e, r.restart((i) => {
    r.stop(), t(i + e);
  }, e, n), r;
}
var mo = Xt("start", "end", "cancel", "interrupt"), vo = [], Yn = 0, nn = 1, Ne = 2, Jt = 3, rn = 4, $e = 5, jt = 6;
function ce(t, e, n, r, i, o) {
  var s = t.__transition;
  if (!s) t.__transition = {};
  else if (n in s) return;
  _o(t, n, {
    name: e,
    index: r,
    // For context during callback.
    group: i,
    // For context during callback.
    on: mo,
    tween: vo,
    time: o.time,
    delay: o.delay,
    duration: o.duration,
    ease: o.ease,
    timer: null,
    state: Yn
  });
}
function De(t, e) {
  var n = ht(t, e);
  if (n.state > Yn) throw new Error("too late; already scheduled");
  return n;
}
function yt(t, e) {
  var n = ht(t, e);
  if (n.state > Jt) throw new Error("too late; already running");
  return n;
}
function ht(t, e) {
  var n = t.__transition;
  if (!n || !(n = n[e])) throw new Error("transition not found");
  return n;
}
function _o(t, e, n) {
  var r = t.__transition, i;
  r[e] = n, n.timer = ze(o, 0, n.time);
  function o(a) {
    n.state = nn, n.timer.restart(s, n.delay, n.time), n.delay <= a && s(a - n.delay);
  }
  function s(a) {
    var l, v, h, d;
    if (n.state !== nn) return c();
    for (l in r)
      if (d = r[l], d.name === n.name) {
        if (d.state === Jt) return en(s);
        d.state === rn ? (d.state = jt, d.timer.stop(), d.on.call("interrupt", t, t.__data__, d.index, d.group), delete r[l]) : +l < e && (d.state = jt, d.timer.stop(), d.on.call("cancel", t, t.__data__, d.index, d.group), delete r[l]);
      }
    if (en(function() {
      n.state === Jt && (n.state = rn, n.timer.restart(u, n.delay, n.time), u(a));
    }), n.state = Ne, n.on.call("start", t, t.__data__, n.index, n.group), n.state === Ne) {
      for (n.state = Jt, i = new Array(h = n.tween.length), l = 0, v = -1; l < h; ++l)
        (d = n.tween[l].value.call(t, t.__data__, n.index, n.group)) && (i[++v] = d);
      i.length = v + 1;
    }
  }
  function u(a) {
    for (var l = a < n.duration ? n.ease.call(null, a / n.duration) : (n.timer.restart(c), n.state = $e, 1), v = -1, h = i.length; ++v < h; )
      i[v].call(t, l);
    n.state === $e && (n.on.call("end", t, t.__data__, n.index, n.group), c());
  }
  function c() {
    n.state = jt, n.timer.stop(), delete r[e];
    for (var a in r) return;
    delete t.__transition;
  }
}
function te(t, e) {
  var n = t.__transition, r, i, o = !0, s;
  if (n) {
    e = e == null ? null : e + "";
    for (s in n) {
      if ((r = n[s]).name !== e) {
        o = !1;
        continue;
      }
      i = r.state > Ne && r.state < $e, r.state = jt, r.timer.stop(), r.on.call(i ? "interrupt" : "cancel", t, t.__data__, r.index, r.group), delete n[s];
    }
    o && delete t.__transition;
  }
}
function xo(t) {
  return this.each(function() {
    te(this, t);
  });
}
function wo(t, e) {
  var n, r;
  return function() {
    var i = yt(this, t), o = i.tween;
    if (o !== n) {
      r = n = o;
      for (var s = 0, u = r.length; s < u; ++s)
        if (r[s].name === e) {
          r = r.slice(), r.splice(s, 1);
          break;
        }
    }
    i.tween = r;
  };
}
function bo(t, e, n) {
  var r, i;
  if (typeof n != "function") throw new Error();
  return function() {
    var o = yt(this, t), s = o.tween;
    if (s !== r) {
      i = (r = s).slice();
      for (var u = { name: e, value: n }, c = 0, a = i.length; c < a; ++c)
        if (i[c].name === e) {
          i[c] = u;
          break;
        }
      c === a && i.push(u);
    }
    o.tween = i;
  };
}
function ko(t, e) {
  var n = this._id;
  if (t += "", arguments.length < 2) {
    for (var r = ht(this.node(), n).tween, i = 0, o = r.length, s; i < o; ++i)
      if ((s = r[i]).name === t)
        return s.value;
    return null;
  }
  return this.each((e == null ? wo : bo)(n, t, e));
}
function Re(t, e, n) {
  var r = t._id;
  return t.each(function() {
    var i = yt(this, r);
    (i.value || (i.value = {}))[e] = n.apply(this, arguments);
  }), function(i) {
    return ht(i, r).value[e];
  };
}
function qn(t, e) {
  var n;
  return (typeof e == "number" ? xt : e instanceof Ht ? Ze : (n = Ht(e)) ? (e = n, Ze) : ro)(t, e);
}
function Eo(t) {
  return function() {
    this.removeAttribute(t);
  };
}
function Mo(t) {
  return function() {
    this.removeAttributeNS(t.space, t.local);
  };
}
function No(t, e, n) {
  var r, i = n + "", o;
  return function() {
    var s = this.getAttribute(t);
    return s === i ? null : s === r ? o : o = e(r = s, n);
  };
}
function $o(t, e, n) {
  var r, i = n + "", o;
  return function() {
    var s = this.getAttributeNS(t.space, t.local);
    return s === i ? null : s === r ? o : o = e(r = s, n);
  };
}
function So(t, e, n) {
  var r, i, o;
  return function() {
    var s, u = n(this), c;
    return u == null ? void this.removeAttribute(t) : (s = this.getAttribute(t), c = u + "", s === c ? null : s === r && c === i ? o : (i = c, o = e(r = s, u)));
  };
}
function Ao(t, e, n) {
  var r, i, o;
  return function() {
    var s, u = n(this), c;
    return u == null ? void this.removeAttributeNS(t.space, t.local) : (s = this.getAttributeNS(t.space, t.local), c = u + "", s === c ? null : s === r && c === i ? o : (i = c, o = e(r = s, u)));
  };
}
function To(t, e) {
  var n = ae(t), r = n === "transform" ? ao : qn;
  return this.attrTween(t, typeof e == "function" ? (n.local ? Ao : So)(n, r, Re(this, "attr." + t, e)) : e == null ? (n.local ? Mo : Eo)(n) : (n.local ? $o : No)(n, r, e));
}
function Co(t, e) {
  return function(n) {
    this.setAttribute(t, e.call(this, n));
  };
}
function zo(t, e) {
  return function(n) {
    this.setAttributeNS(t.space, t.local, e.call(this, n));
  };
}
function Do(t, e) {
  var n, r;
  function i() {
    var o = e.apply(this, arguments);
    return o !== r && (n = (r = o) && zo(t, o)), n;
  }
  return i._value = e, i;
}
function Ro(t, e) {
  var n, r;
  function i() {
    var o = e.apply(this, arguments);
    return o !== r && (n = (r = o) && Co(t, o)), n;
  }
  return i._value = e, i;
}
function Io(t, e) {
  var n = "attr." + t;
  if (arguments.length < 2) return (n = this.tween(n)) && n._value;
  if (e == null) return this.tween(n, null);
  if (typeof e != "function") throw new Error();
  var r = ae(t);
  return this.tween(n, (r.local ? Do : Ro)(r, e));
}
function Lo(t, e) {
  return function() {
    De(this, t).delay = +e.apply(this, arguments);
  };
}
function Fo(t, e) {
  return e = +e, function() {
    De(this, t).delay = e;
  };
}
function Oo(t) {
  var e = this._id;
  return arguments.length ? this.each((typeof t == "function" ? Lo : Fo)(e, t)) : ht(this.node(), e).delay;
}
function Ko(t, e) {
  return function() {
    yt(this, t).duration = +e.apply(this, arguments);
  };
}
function Ho(t, e) {
  return e = +e, function() {
    yt(this, t).duration = e;
  };
}
function Po(t) {
  var e = this._id;
  return arguments.length ? this.each((typeof t == "function" ? Ko : Ho)(e, t)) : ht(this.node(), e).duration;
}
function Xo(t, e) {
  if (typeof e != "function") throw new Error();
  return function() {
    yt(this, t).ease = e;
  };
}
function Yo(t) {
  var e = this._id;
  return arguments.length ? this.each(Xo(e, t)) : ht(this.node(), e).ease;
}
function qo(t, e) {
  return function() {
    var n = e.apply(this, arguments);
    if (typeof n != "function") throw new Error();
    yt(this, t).ease = n;
  };
}
function Bo(t) {
  if (typeof t != "function") throw new Error();
  return this.each(qo(this._id, t));
}
function Vo(t) {
  typeof t != "function" && (t = kn(t));
  for (var e = this._groups, n = e.length, r = new Array(n), i = 0; i < n; ++i)
    for (var o = e[i], s = o.length, u = r[i] = [], c, a = 0; a < s; ++a)
      (c = o[a]) && t.call(c, c.__data__, a, o) && u.push(c);
  return new _t(r, this._parents, this._name, this._id);
}
function Go(t) {
  if (t._id !== this._id) throw new Error();
  for (var e = this._groups, n = t._groups, r = e.length, i = n.length, o = Math.min(r, i), s = new Array(r), u = 0; u < o; ++u)
    for (var c = e[u], a = n[u], l = c.length, v = s[u] = new Array(l), h, d = 0; d < l; ++d)
      (h = c[d] || a[d]) && (v[d] = h);
  for (; u < r; ++u)
    s[u] = e[u];
  return new _t(s, this._parents, this._name, this._id);
}
function Uo(t) {
  return (t + "").trim().split(/^|\s+/).every(function(e) {
    var n = e.indexOf(".");
    return n >= 0 && (e = e.slice(0, n)), !e || e === "start";
  });
}
function Wo(t, e, n) {
  var r, i, o = Uo(e) ? De : yt;
  return function() {
    var s = o(this, t), u = s.on;
    u !== r && (i = (r = u).copy()).on(e, n), s.on = i;
  };
}
function Qo(t, e) {
  var n = this._id;
  return arguments.length < 2 ? ht(this.node(), n).on.on(t) : this.each(Wo(n, t, e));
}
function Zo(t) {
  return function() {
    var e = this.parentNode;
    for (var n in this.__transition) if (+n !== t) return;
    e && e.removeChild(this);
  };
}
function Jo() {
  return this.on("end.remove", Zo(this._id));
}
function jo(t) {
  var e = this._name, n = this._id;
  typeof t != "function" && (t = Se(t));
  for (var r = this._groups, i = r.length, o = new Array(i), s = 0; s < i; ++s)
    for (var u = r[s], c = u.length, a = o[s] = new Array(c), l, v, h = 0; h < c; ++h)
      (l = u[h]) && (v = t.call(l, l.__data__, h, u)) && ("__data__" in l && (v.__data__ = l.__data__), a[h] = v, ce(a[h], e, n, h, a, ht(l, n)));
  return new _t(o, this._parents, e, n);
}
function ts(t) {
  var e = this._name, n = this._id;
  typeof t != "function" && (t = bn(t));
  for (var r = this._groups, i = r.length, o = [], s = [], u = 0; u < i; ++u)
    for (var c = r[u], a = c.length, l, v = 0; v < a; ++v)
      if (l = c[v]) {
        for (var h = t.call(l, l.__data__, v, c), d, k = ht(l, n), _ = 0, f = h.length; _ < f; ++_)
          (d = h[_]) && ce(d, e, n, _, h, k);
        o.push(h), s.push(l);
      }
  return new _t(o, s, e, n);
}
var es = Yt.prototype.constructor;
function ns() {
  return new es(this._groups, this._parents);
}
function rs(t, e) {
  var n, r, i;
  return function() {
    var o = Tt(this, t), s = (this.style.removeProperty(t), Tt(this, t));
    return o === s ? null : o === n && s === r ? i : i = e(n = o, r = s);
  };
}
function Bn(t) {
  return function() {
    this.style.removeProperty(t);
  };
}
function is(t, e, n) {
  var r, i = n + "", o;
  return function() {
    var s = Tt(this, t);
    return s === i ? null : s === r ? o : o = e(r = s, n);
  };
}
function os(t, e, n) {
  var r, i, o;
  return function() {
    var s = Tt(this, t), u = n(this), c = u + "";
    return u == null && (c = u = (this.style.removeProperty(t), Tt(this, t))), s === c ? null : s === r && c === i ? o : (i = c, o = e(r = s, u));
  };
}
function ss(t, e) {
  var n, r, i, o = "style." + e, s = "end." + o, u;
  return function() {
    var c = yt(this, t), a = c.on, l = c.value[o] == null ? u || (u = Bn(e)) : void 0;
    (a !== n || i !== l) && (r = (n = a).copy()).on(s, i = l), c.on = r;
  };
}
function as(t, e, n) {
  var r = (t += "") == "transform" ? so : qn;
  return e == null ? this.styleTween(t, rs(t, r)).on("end.style." + t, Bn(t)) : typeof e == "function" ? this.styleTween(t, os(t, r, Re(this, "style." + t, e))).each(ss(this._id, t)) : this.styleTween(t, is(t, r, e), n).on("end.style." + t, null);
}
function us(t, e, n) {
  return function(r) {
    this.style.setProperty(t, e.call(this, r), n);
  };
}
function cs(t, e, n) {
  var r, i;
  function o() {
    var s = e.apply(this, arguments);
    return s !== i && (r = (i = s) && us(t, s, n)), r;
  }
  return o._value = e, o;
}
function ls(t, e, n) {
  var r = "style." + (t += "");
  if (arguments.length < 2) return (r = this.tween(r)) && r._value;
  if (e == null) return this.tween(r, null);
  if (typeof e != "function") throw new Error();
  return this.tween(r, cs(t, e, n ?? ""));
}
function fs(t) {
  return function() {
    this.textContent = t;
  };
}
function hs(t) {
  return function() {
    var e = t(this);
    this.textContent = e ?? "";
  };
}
function gs(t) {
  return this.tween("text", typeof t == "function" ? hs(Re(this, "text", t)) : fs(t == null ? "" : t + ""));
}
function ds(t) {
  return function(e) {
    this.textContent = t.call(this, e);
  };
}
function ys(t) {
  var e, n;
  function r() {
    var i = t.apply(this, arguments);
    return i !== n && (e = (n = i) && ds(i)), e;
  }
  return r._value = t, r;
}
function ps(t) {
  var e = "text";
  if (arguments.length < 1) return (e = this.tween(e)) && e._value;
  if (t == null) return this.tween(e, null);
  if (typeof t != "function") throw new Error();
  return this.tween(e, ys(t));
}
function ms() {
  for (var t = this._name, e = this._id, n = Vn(), r = this._groups, i = r.length, o = 0; o < i; ++o)
    for (var s = r[o], u = s.length, c, a = 0; a < u; ++a)
      if (c = s[a]) {
        var l = ht(c, e);
        ce(c, t, n, a, s, {
          time: l.time + l.delay + l.duration,
          delay: 0,
          duration: l.duration,
          ease: l.ease
        });
      }
  return new _t(r, this._parents, t, n);
}
function vs() {
  var t, e, n = this, r = n._id, i = n.size();
  return new Promise(function(o, s) {
    var u = { value: s }, c = { value: function() {
      --i === 0 && o();
    } };
    n.each(function() {
      var a = yt(this, r), l = a.on;
      l !== t && (e = (t = l).copy(), e._.cancel.push(u), e._.interrupt.push(u), e._.end.push(c)), a.on = e;
    }), i === 0 && o();
  });
}
var _s = 0;
function _t(t, e, n, r) {
  this._groups = t, this._parents = e, this._name = n, this._id = r;
}
function Vn() {
  return ++_s;
}
var pt = Yt.prototype;
_t.prototype = {
  constructor: _t,
  select: jo,
  selectAll: ts,
  selectChild: pt.selectChild,
  selectChildren: pt.selectChildren,
  filter: Vo,
  merge: Go,
  selection: ns,
  transition: ms,
  call: pt.call,
  nodes: pt.nodes,
  node: pt.node,
  size: pt.size,
  empty: pt.empty,
  each: pt.each,
  on: Qo,
  attr: To,
  attrTween: Io,
  style: as,
  styleTween: ls,
  text: gs,
  textTween: ps,
  remove: Jo,
  tween: ko,
  delay: Oo,
  duration: Po,
  ease: Yo,
  easeVarying: Bo,
  end: vs,
  [Symbol.iterator]: pt[Symbol.iterator]
};
function Gn(t) {
  return ((t *= 2) <= 1 ? t * t * t : (t -= 2) * t * t + 2) / 2;
}
var xs = {
  time: null,
  // Set on use.
  delay: 0,
  duration: 250,
  ease: Gn
};
function ws(t, e) {
  for (var n; !(n = t.__transition) || !(n = n[e]); )
    if (!(t = t.parentNode))
      throw new Error(`transition ${e} not found`);
  return n;
}
function bs(t) {
  var e, n;
  t instanceof _t ? (e = t._id, t = t._name) : (e = Vn(), (n = xs).time = Ce(), t = t == null ? null : t + "");
  for (var r = this._groups, i = r.length, o = 0; o < i; ++o)
    for (var s = r[o], u = s.length, c, a = 0; a < u; ++a)
      (c = s[a]) && ce(c, t, e, a, s, n || ws(c, e));
  return new _t(r, this._parents, t, e);
}
Yt.prototype.interrupt = xo;
Yt.prototype.transition = bs;
function ks(t, e) {
  var n, r = 1;
  t == null && (t = 0), e == null && (e = 0);
  function i() {
    var o, s = n.length, u, c = 0, a = 0;
    for (o = 0; o < s; ++o)
      u = n[o], c += u.x, a += u.y;
    for (c = (c / s - t) * r, a = (a / s - e) * r, o = 0; o < s; ++o)
      u = n[o], u.x -= c, u.y -= a;
  }
  return i.initialize = function(o) {
    n = o;
  }, i.x = function(o) {
    return arguments.length ? (t = +o, i) : t;
  }, i.y = function(o) {
    return arguments.length ? (e = +o, i) : e;
  }, i.strength = function(o) {
    return arguments.length ? (r = +o, i) : r;
  }, i;
}
function Es(t) {
  const e = +this._x.call(null, t), n = +this._y.call(null, t);
  return Un(this.cover(e, n), e, n, t);
}
function Un(t, e, n, r) {
  if (isNaN(e) || isNaN(n)) return t;
  var i, o = t._root, s = { data: r }, u = t._x0, c = t._y0, a = t._x1, l = t._y1, v, h, d, k, _, f, m, M;
  if (!o) return t._root = s, t;
  for (; o.length; )
    if ((_ = e >= (v = (u + a) / 2)) ? u = v : a = v, (f = n >= (h = (c + l) / 2)) ? c = h : l = h, i = o, !(o = o[m = f << 1 | _])) return i[m] = s, t;
  if (d = +t._x.call(null, o.data), k = +t._y.call(null, o.data), e === d && n === k) return s.next = o, i ? i[m] = s : t._root = s, t;
  do
    i = i ? i[m] = new Array(4) : t._root = new Array(4), (_ = e >= (v = (u + a) / 2)) ? u = v : a = v, (f = n >= (h = (c + l) / 2)) ? c = h : l = h;
  while ((m = f << 1 | _) === (M = (k >= h) << 1 | d >= v));
  return i[M] = o, i[m] = s, t;
}
function Ms(t) {
  var e, n, r = t.length, i, o, s = new Array(r), u = new Array(r), c = 1 / 0, a = 1 / 0, l = -1 / 0, v = -1 / 0;
  for (n = 0; n < r; ++n)
    isNaN(i = +this._x.call(null, e = t[n])) || isNaN(o = +this._y.call(null, e)) || (s[n] = i, u[n] = o, i < c && (c = i), i > l && (l = i), o < a && (a = o), o > v && (v = o));
  if (c > l || a > v) return this;
  for (this.cover(c, a).cover(l, v), n = 0; n < r; ++n)
    Un(this, s[n], u[n], t[n]);
  return this;
}
function Ns(t, e) {
  if (isNaN(t = +t) || isNaN(e = +e)) return this;
  var n = this._x0, r = this._y0, i = this._x1, o = this._y1;
  if (isNaN(n))
    i = (n = Math.floor(t)) + 1, o = (r = Math.floor(e)) + 1;
  else {
    for (var s = i - n || 1, u = this._root, c, a; n > t || t >= i || r > e || e >= o; )
      switch (a = (e < r) << 1 | t < n, c = new Array(4), c[a] = u, u = c, s *= 2, a) {
        case 0:
          i = n + s, o = r + s;
          break;
        case 1:
          n = i - s, o = r + s;
          break;
        case 2:
          i = n + s, r = o - s;
          break;
        case 3:
          n = i - s, r = o - s;
          break;
      }
    this._root && this._root.length && (this._root = u);
  }
  return this._x0 = n, this._y0 = r, this._x1 = i, this._y1 = o, this;
}
function $s() {
  var t = [];
  return this.visit(function(e) {
    if (!e.length) do
      t.push(e.data);
    while (e = e.next);
  }), t;
}
function Ss(t) {
  return arguments.length ? this.cover(+t[0][0], +t[0][1]).cover(+t[1][0], +t[1][1]) : isNaN(this._x0) ? void 0 : [[this._x0, this._y0], [this._x1, this._y1]];
}
function j(t, e, n, r, i) {
  this.node = t, this.x0 = e, this.y0 = n, this.x1 = r, this.y1 = i;
}
function As(t, e, n) {
  var r, i = this._x0, o = this._y0, s, u, c, a, l = this._x1, v = this._y1, h = [], d = this._root, k, _;
  for (d && h.push(new j(d, i, o, l, v)), n == null ? n = 1 / 0 : (i = t - n, o = e - n, l = t + n, v = e + n, n *= n); k = h.pop(); )
    if (!(!(d = k.node) || (s = k.x0) > l || (u = k.y0) > v || (c = k.x1) < i || (a = k.y1) < o))
      if (d.length) {
        var f = (s + c) / 2, m = (u + a) / 2;
        h.push(
          new j(d[3], f, m, c, a),
          new j(d[2], s, m, f, a),
          new j(d[1], f, u, c, m),
          new j(d[0], s, u, f, m)
        ), (_ = (e >= m) << 1 | t >= f) && (k = h[h.length - 1], h[h.length - 1] = h[h.length - 1 - _], h[h.length - 1 - _] = k);
      } else {
        var M = t - +this._x.call(null, d.data), C = e - +this._y.call(null, d.data), p = M * M + C * C;
        if (p < n) {
          var T = Math.sqrt(n = p);
          i = t - T, o = e - T, l = t + T, v = e + T, r = d.data;
        }
      }
  return r;
}
function Ts(t) {
  if (isNaN(l = +this._x.call(null, t)) || isNaN(v = +this._y.call(null, t))) return this;
  var e, n = this._root, r, i, o, s = this._x0, u = this._y0, c = this._x1, a = this._y1, l, v, h, d, k, _, f, m;
  if (!n) return this;
  if (n.length) for (; ; ) {
    if ((k = l >= (h = (s + c) / 2)) ? s = h : c = h, (_ = v >= (d = (u + a) / 2)) ? u = d : a = d, e = n, !(n = n[f = _ << 1 | k])) return this;
    if (!n.length) break;
    (e[f + 1 & 3] || e[f + 2 & 3] || e[f + 3 & 3]) && (r = e, m = f);
  }
  for (; n.data !== t; ) if (i = n, !(n = n.next)) return this;
  return (o = n.next) && delete n.next, i ? (o ? i.next = o : delete i.next, this) : e ? (o ? e[f] = o : delete e[f], (n = e[0] || e[1] || e[2] || e[3]) && n === (e[3] || e[2] || e[1] || e[0]) && !n.length && (r ? r[m] = n : this._root = n), this) : (this._root = o, this);
}
function Cs(t) {
  for (var e = 0, n = t.length; e < n; ++e) this.remove(t[e]);
  return this;
}
function zs() {
  return this._root;
}
function Ds() {
  var t = 0;
  return this.visit(function(e) {
    if (!e.length) do
      ++t;
    while (e = e.next);
  }), t;
}
function Rs(t) {
  var e = [], n, r = this._root, i, o, s, u, c;
  for (r && e.push(new j(r, this._x0, this._y0, this._x1, this._y1)); n = e.pop(); )
    if (!t(r = n.node, o = n.x0, s = n.y0, u = n.x1, c = n.y1) && r.length) {
      var a = (o + u) / 2, l = (s + c) / 2;
      (i = r[3]) && e.push(new j(i, a, l, u, c)), (i = r[2]) && e.push(new j(i, o, l, a, c)), (i = r[1]) && e.push(new j(i, a, s, u, l)), (i = r[0]) && e.push(new j(i, o, s, a, l));
    }
  return this;
}
function Is(t) {
  var e = [], n = [], r;
  for (this._root && e.push(new j(this._root, this._x0, this._y0, this._x1, this._y1)); r = e.pop(); ) {
    var i = r.node;
    if (i.length) {
      var o, s = r.x0, u = r.y0, c = r.x1, a = r.y1, l = (s + c) / 2, v = (u + a) / 2;
      (o = i[0]) && e.push(new j(o, s, u, l, v)), (o = i[1]) && e.push(new j(o, l, u, c, v)), (o = i[2]) && e.push(new j(o, s, v, l, a)), (o = i[3]) && e.push(new j(o, l, v, c, a));
    }
    n.push(r);
  }
  for (; r = n.pop(); )
    t(r.node, r.x0, r.y0, r.x1, r.y1);
  return this;
}
function Ls(t) {
  return t[0];
}
function Fs(t) {
  return arguments.length ? (this._x = t, this) : this._x;
}
function Os(t) {
  return t[1];
}
function Ks(t) {
  return arguments.length ? (this._y = t, this) : this._y;
}
function Ie(t, e, n) {
  var r = new Le(e ?? Ls, n ?? Os, NaN, NaN, NaN, NaN);
  return t == null ? r : r.addAll(t);
}
function Le(t, e, n, r, i, o) {
  this._x = t, this._y = e, this._x0 = n, this._y0 = r, this._x1 = i, this._y1 = o, this._root = void 0;
}
function on(t) {
  for (var e = { data: t.data }, n = e; t = t.next; ) n = n.next = { data: t.data };
  return e;
}
var tt = Ie.prototype = Le.prototype;
tt.copy = function() {
  var t = new Le(this._x, this._y, this._x0, this._y0, this._x1, this._y1), e = this._root, n, r;
  if (!e) return t;
  if (!e.length) return t._root = on(e), t;
  for (n = [{ source: e, target: t._root = new Array(4) }]; e = n.pop(); )
    for (var i = 0; i < 4; ++i)
      (r = e.source[i]) && (r.length ? n.push({ source: r, target: e.target[i] = new Array(4) }) : e.target[i] = on(r));
  return t;
};
tt.add = Es;
tt.addAll = Ms;
tt.cover = Ns;
tt.data = $s;
tt.extent = Ss;
tt.find = As;
tt.remove = Ts;
tt.removeAll = Cs;
tt.root = zs;
tt.size = Ds;
tt.visit = Rs;
tt.visitAfter = Is;
tt.x = Fs;
tt.y = Ks;
function ft(t) {
  return function() {
    return t;
  };
}
function wt(t) {
  return (t() - 0.5) * 1e-6;
}
function Hs(t) {
  return t.x + t.vx;
}
function Ps(t) {
  return t.y + t.vy;
}
function Xs(t) {
  var e, n, r, i = 1, o = 1;
  typeof t != "function" && (t = ft(t == null ? 1 : +t));
  function s() {
    for (var a, l = e.length, v, h, d, k, _, f, m = 0; m < o; ++m)
      for (v = Ie(e, Hs, Ps).visitAfter(u), a = 0; a < l; ++a)
        h = e[a], _ = n[h.index], f = _ * _, d = h.x + h.vx, k = h.y + h.vy, v.visit(M);
    function M(C, p, T, x, $) {
      var D = C.data, K = C.r, H = _ + K;
      if (D) {
        if (D.index > h.index) {
          var q = d - D.x - D.vx, Q = k - D.y - D.vy, W = q * q + Q * Q;
          W < H * H && (q === 0 && (q = wt(r), W += q * q), Q === 0 && (Q = wt(r), W += Q * Q), W = (H - (W = Math.sqrt(W))) / W * i, h.vx += (q *= W) * (H = (K *= K) / (f + K)), h.vy += (Q *= W) * H, D.vx -= q * (H = 1 - H), D.vy -= Q * H);
        }
        return;
      }
      return p > d + H || x < d - H || T > k + H || $ < k - H;
    }
  }
  function u(a) {
    if (a.data) return a.r = n[a.data.index];
    for (var l = a.r = 0; l < 4; ++l)
      a[l] && a[l].r > a.r && (a.r = a[l].r);
  }
  function c() {
    if (e) {
      var a, l = e.length, v;
      for (n = new Array(l), a = 0; a < l; ++a) v = e[a], n[v.index] = +t(v, a, e);
    }
  }
  return s.initialize = function(a, l) {
    e = a, r = l, c();
  }, s.iterations = function(a) {
    return arguments.length ? (o = +a, s) : o;
  }, s.strength = function(a) {
    return arguments.length ? (i = +a, s) : i;
  }, s.radius = function(a) {
    return arguments.length ? (t = typeof a == "function" ? a : ft(+a), c(), s) : t;
  }, s;
}
function Ys(t) {
  return t.index;
}
function sn(t, e) {
  var n = t.get(e);
  if (!n) throw new Error("node not found: " + e);
  return n;
}
function qs(t) {
  var e = Ys, n = v, r, i = ft(30), o, s, u, c, a, l = 1;
  t == null && (t = []);
  function v(f) {
    return 1 / Math.min(u[f.source.index], u[f.target.index]);
  }
  function h(f) {
    for (var m = 0, M = t.length; m < l; ++m)
      for (var C = 0, p, T, x, $, D, K, H; C < M; ++C)
        p = t[C], T = p.source, x = p.target, $ = x.x + x.vx - T.x - T.vx || wt(a), D = x.y + x.vy - T.y - T.vy || wt(a), K = Math.sqrt($ * $ + D * D), K = (K - o[C]) / K * f * r[C], $ *= K, D *= K, x.vx -= $ * (H = c[C]), x.vy -= D * H, T.vx += $ * (H = 1 - H), T.vy += D * H;
  }
  function d() {
    if (s) {
      var f, m = s.length, M = t.length, C = new Map(s.map((T, x) => [e(T, x, s), T])), p;
      for (f = 0, u = new Array(m); f < M; ++f)
        p = t[f], p.index = f, typeof p.source != "object" && (p.source = sn(C, p.source)), typeof p.target != "object" && (p.target = sn(C, p.target)), u[p.source.index] = (u[p.source.index] || 0) + 1, u[p.target.index] = (u[p.target.index] || 0) + 1;
      for (f = 0, c = new Array(M); f < M; ++f)
        p = t[f], c[f] = u[p.source.index] / (u[p.source.index] + u[p.target.index]);
      r = new Array(M), k(), o = new Array(M), _();
    }
  }
  function k() {
    if (s)
      for (var f = 0, m = t.length; f < m; ++f)
        r[f] = +n(t[f], f, t);
  }
  function _() {
    if (s)
      for (var f = 0, m = t.length; f < m; ++f)
        o[f] = +i(t[f], f, t);
  }
  return h.initialize = function(f, m) {
    s = f, a = m, d();
  }, h.links = function(f) {
    return arguments.length ? (t = f, d(), h) : t;
  }, h.id = function(f) {
    return arguments.length ? (e = f, h) : e;
  }, h.iterations = function(f) {
    return arguments.length ? (l = +f, h) : l;
  }, h.strength = function(f) {
    return arguments.length ? (n = typeof f == "function" ? f : ft(+f), k(), h) : n;
  }, h.distance = function(f) {
    return arguments.length ? (i = typeof f == "function" ? f : ft(+f), _(), h) : i;
  }, h;
}
const Bs = 1664525, Vs = 1013904223, an = 4294967296;
function Gs() {
  let t = 1;
  return () => (t = (Bs * t + Vs) % an) / an;
}
function Us(t) {
  return t.x;
}
function Ws(t) {
  return t.y;
}
var Qs = 10, Zs = Math.PI * (3 - Math.sqrt(5));
function Js(t) {
  var e, n = 1, r = 1e-3, i = 1 - Math.pow(r, 1 / 300), o = 0, s = 0.6, u = /* @__PURE__ */ new Map(), c = ze(v), a = Xt("tick", "end"), l = Gs();
  t == null && (t = []);
  function v() {
    h(), a.call("tick", e), n < r && (c.stop(), a.call("end", e));
  }
  function h(_) {
    var f, m = t.length, M;
    _ === void 0 && (_ = 1);
    for (var C = 0; C < _; ++C)
      for (n += (o - n) * i, u.forEach(function(p) {
        p(n);
      }), f = 0; f < m; ++f)
        M = t[f], M.fx == null ? M.x += M.vx *= s : (M.x = M.fx, M.vx = 0), M.fy == null ? M.y += M.vy *= s : (M.y = M.fy, M.vy = 0);
    return e;
  }
  function d() {
    for (var _ = 0, f = t.length, m; _ < f; ++_) {
      if (m = t[_], m.index = _, m.fx != null && (m.x = m.fx), m.fy != null && (m.y = m.fy), isNaN(m.x) || isNaN(m.y)) {
        var M = Qs * Math.sqrt(0.5 + _), C = _ * Zs;
        m.x = M * Math.cos(C), m.y = M * Math.sin(C);
      }
      (isNaN(m.vx) || isNaN(m.vy)) && (m.vx = m.vy = 0);
    }
  }
  function k(_) {
    return _.initialize && _.initialize(t, l), _;
  }
  return d(), e = {
    tick: h,
    restart: function() {
      return c.restart(v), e;
    },
    stop: function() {
      return c.stop(), e;
    },
    nodes: function(_) {
      return arguments.length ? (t = _, d(), u.forEach(k), e) : t;
    },
    alpha: function(_) {
      return arguments.length ? (n = +_, e) : n;
    },
    alphaMin: function(_) {
      return arguments.length ? (r = +_, e) : r;
    },
    alphaDecay: function(_) {
      return arguments.length ? (i = +_, e) : +i;
    },
    alphaTarget: function(_) {
      return arguments.length ? (o = +_, e) : o;
    },
    velocityDecay: function(_) {
      return arguments.length ? (s = 1 - _, e) : 1 - s;
    },
    randomSource: function(_) {
      return arguments.length ? (l = _, u.forEach(k), e) : l;
    },
    force: function(_, f) {
      return arguments.length > 1 ? (f == null ? u.delete(_) : u.set(_, k(f)), e) : u.get(_);
    },
    find: function(_, f, m) {
      var M = 0, C = t.length, p, T, x, $, D;
      for (m == null ? m = 1 / 0 : m *= m, M = 0; M < C; ++M)
        $ = t[M], p = _ - $.x, T = f - $.y, x = p * p + T * T, x < m && (D = $, m = x);
      return D;
    },
    on: function(_, f) {
      return arguments.length > 1 ? (a.on(_, f), e) : a.on(_);
    }
  };
}
function js() {
  var t, e, n, r, i = ft(-30), o, s = 1, u = 1 / 0, c = 0.81;
  function a(d) {
    var k, _ = t.length, f = Ie(t, Us, Ws).visitAfter(v);
    for (r = d, k = 0; k < _; ++k) e = t[k], f.visit(h);
  }
  function l() {
    if (t) {
      var d, k = t.length, _;
      for (o = new Array(k), d = 0; d < k; ++d) _ = t[d], o[_.index] = +i(_, d, t);
    }
  }
  function v(d) {
    var k = 0, _, f, m = 0, M, C, p;
    if (d.length) {
      for (M = C = p = 0; p < 4; ++p)
        (_ = d[p]) && (f = Math.abs(_.value)) && (k += _.value, m += f, M += f * _.x, C += f * _.y);
      d.x = M / m, d.y = C / m;
    } else {
      _ = d, _.x = _.data.x, _.y = _.data.y;
      do
        k += o[_.data.index];
      while (_ = _.next);
    }
    d.value = k;
  }
  function h(d, k, _, f) {
    if (!d.value) return !0;
    var m = d.x - e.x, M = d.y - e.y, C = f - k, p = m * m + M * M;
    if (C * C / c < p)
      return p < u && (m === 0 && (m = wt(n), p += m * m), M === 0 && (M = wt(n), p += M * M), p < s && (p = Math.sqrt(s * p)), e.vx += m * d.value * r / p, e.vy += M * d.value * r / p), !0;
    if (d.length || p >= u) return;
    (d.data !== e || d.next) && (m === 0 && (m = wt(n), p += m * m), M === 0 && (M = wt(n), p += M * M), p < s && (p = Math.sqrt(s * p)));
    do
      d.data !== e && (C = o[d.data.index] * r / p, e.vx += m * C, e.vy += M * C);
    while (d = d.next);
  }
  return a.initialize = function(d, k) {
    t = d, n = k, l();
  }, a.strength = function(d) {
    return arguments.length ? (i = typeof d == "function" ? d : ft(+d), l(), a) : i;
  }, a.distanceMin = function(d) {
    return arguments.length ? (s = d * d, a) : Math.sqrt(s);
  }, a.distanceMax = function(d) {
    return arguments.length ? (u = d * d, a) : Math.sqrt(u);
  }, a.theta = function(d) {
    return arguments.length ? (c = d * d, a) : Math.sqrt(c);
  }, a;
}
function un(t, e, n) {
  var r, i = ft(0.1), o, s;
  typeof t != "function" && (t = ft(+t)), e == null && (e = 0), n == null && (n = 0);
  function u(a) {
    for (var l = 0, v = r.length; l < v; ++l) {
      var h = r[l], d = h.x - e || 1e-6, k = h.y - n || 1e-6, _ = Math.sqrt(d * d + k * k), f = (s[l] - _) * o[l] * a / _;
      h.vx += d * f, h.vy += k * f;
    }
  }
  function c() {
    if (r) {
      var a, l = r.length;
      for (o = new Array(l), s = new Array(l), a = 0; a < l; ++a)
        s[a] = +t(r[a], a, r), o[a] = isNaN(s[a]) ? 0 : +i(r[a], a, r);
    }
  }
  return u.initialize = function(a) {
    r = a, c();
  }, u.strength = function(a) {
    return arguments.length ? (i = typeof a == "function" ? a : ft(+a), c(), u) : i;
  }, u.radius = function(a) {
    return arguments.length ? (t = typeof a == "function" ? a : ft(+a), c(), u) : t;
  }, u.x = function(a) {
    return arguments.length ? (e = +a, u) : e;
  }, u.y = function(a) {
    return arguments.length ? (n = +a, u) : n;
  }, u;
}
const ta = 1664525, ea = 1013904223, cn = 1 / 4294967296;
function na(t = Math.random()) {
  let e = (0 <= t && t < 1 ? t / cn : Math.abs(t)) | 0;
  return () => (e = ta * e + ea | 0, cn * (e >>> 0));
}
const Qt = (t) => () => t;
function ra(t, {
  sourceEvent: e,
  target: n,
  transform: r,
  dispatch: i
}) {
  Object.defineProperties(this, {
    type: { value: t, enumerable: !0, configurable: !0 },
    sourceEvent: { value: e, enumerable: !0, configurable: !0 },
    target: { value: n, enumerable: !0, configurable: !0 },
    transform: { value: r, enumerable: !0, configurable: !0 },
    _: { value: i }
  });
}
function vt(t, e, n) {
  this.k = t, this.x = e, this.y = n;
}
vt.prototype = {
  constructor: vt,
  scale: function(t) {
    return t === 1 ? this : new vt(this.k * t, this.x, this.y);
  },
  translate: function(t, e) {
    return t === 0 & e === 0 ? this : new vt(this.k, this.x + this.k * t, this.y + this.k * e);
  },
  apply: function(t) {
    return [t[0] * this.k + this.x, t[1] * this.k + this.y];
  },
  applyX: function(t) {
    return t * this.k + this.x;
  },
  applyY: function(t) {
    return t * this.k + this.y;
  },
  invert: function(t) {
    return [(t[0] - this.x) / this.k, (t[1] - this.y) / this.k];
  },
  invertX: function(t) {
    return (t - this.x) / this.k;
  },
  invertY: function(t) {
    return (t - this.y) / this.k;
  },
  rescaleX: function(t) {
    return t.copy().domain(t.range().map(this.invertX, this).map(t.invert, t));
  },
  rescaleY: function(t) {
    return t.copy().domain(t.range().map(this.invertY, this).map(t.invert, t));
  },
  toString: function() {
    return "translate(" + this.x + "," + this.y + ") scale(" + this.k + ")";
  }
};
var Fe = new vt(1, 0, 0);
vt.prototype;
function de(t) {
  t.stopImmediatePropagation();
}
function Dt(t) {
  t.preventDefault(), t.stopImmediatePropagation();
}
function ia(t) {
  return (!t.ctrlKey || t.type === "wheel") && !t.button;
}
function oa() {
  var t = this;
  return t instanceof SVGElement ? (t = t.ownerSVGElement || t, t.hasAttribute("viewBox") ? (t = t.viewBox.baseVal, [[t.x, t.y], [t.x + t.width, t.y + t.height]]) : [[0, 0], [t.width.baseVal.value, t.height.baseVal.value]]) : [[0, 0], [t.clientWidth, t.clientHeight]];
}
function ln() {
  return this.__zoom || Fe;
}
function sa(t) {
  return -t.deltaY * (t.deltaMode === 1 ? 0.05 : t.deltaMode ? 1 : 2e-3) * (t.ctrlKey ? 10 : 1);
}
function aa() {
  return navigator.maxTouchPoints || "ontouchstart" in this;
}
function ua(t, e, n) {
  var r = t.invertX(e[0][0]) - n[0][0], i = t.invertX(e[1][0]) - n[1][0], o = t.invertY(e[0][1]) - n[0][1], s = t.invertY(e[1][1]) - n[1][1];
  return t.translate(
    i > r ? (r + i) / 2 : Math.min(0, r) || Math.max(0, i),
    s > o ? (o + s) / 2 : Math.min(0, o) || Math.max(0, s)
  );
}
function ca() {
  var t = ia, e = oa, n = ua, r = sa, i = aa, o = [0, 1 / 0], s = [[-1 / 0, -1 / 0], [1 / 0, 1 / 0]], u = 250, c = fo, a = Xt("start", "zoom", "end"), l, v, h, d = 500, k = 150, _ = 0, f = 10;
  function m(y) {
    y.property("__zoom", ln).on("wheel.zoom", D, { passive: !1 }).on("mousedown.zoom", K).on("dblclick.zoom", H).filter(i).on("touchstart.zoom", q).on("touchmove.zoom", Q).on("touchend.zoom touchcancel.zoom", W).style("-webkit-tap-highlight-color", "rgba(0,0,0,0)");
  }
  m.transform = function(y, S, w, z) {
    var R = y.selection ? y.selection() : y;
    R.property("__zoom", ln), y !== R ? T(y, S, w, z) : R.interrupt().each(function() {
      x(this, arguments).event(z).start().zoom(null, typeof S == "function" ? S.apply(this, arguments) : S).end();
    });
  }, m.scaleBy = function(y, S, w, z) {
    m.scaleTo(y, function() {
      var R = this.__zoom.k, I = typeof S == "function" ? S.apply(this, arguments) : S;
      return R * I;
    }, w, z);
  }, m.scaleTo = function(y, S, w, z) {
    m.transform(y, function() {
      var R = e.apply(this, arguments), I = this.__zoom, F = w == null ? p(R) : typeof w == "function" ? w.apply(this, arguments) : w, O = I.invert(F), X = typeof S == "function" ? S.apply(this, arguments) : S;
      return n(C(M(I, X), F, O), R, s);
    }, w, z);
  }, m.translateBy = function(y, S, w, z) {
    m.transform(y, function() {
      return n(this.__zoom.translate(
        typeof S == "function" ? S.apply(this, arguments) : S,
        typeof w == "function" ? w.apply(this, arguments) : w
      ), e.apply(this, arguments), s);
    }, null, z);
  }, m.translateTo = function(y, S, w, z, R) {
    m.transform(y, function() {
      var I = e.apply(this, arguments), F = this.__zoom, O = z == null ? p(I) : typeof z == "function" ? z.apply(this, arguments) : z;
      return n(Fe.translate(O[0], O[1]).scale(F.k).translate(
        typeof S == "function" ? -S.apply(this, arguments) : -S,
        typeof w == "function" ? -w.apply(this, arguments) : -w
      ), I, s);
    }, z, R);
  };
  function M(y, S) {
    return S = Math.max(o[0], Math.min(o[1], S)), S === y.k ? y : new vt(S, y.x, y.y);
  }
  function C(y, S, w) {
    var z = S[0] - w[0] * y.k, R = S[1] - w[1] * y.k;
    return z === y.x && R === y.y ? y : new vt(y.k, z, R);
  }
  function p(y) {
    return [(+y[0][0] + +y[1][0]) / 2, (+y[0][1] + +y[1][1]) / 2];
  }
  function T(y, S, w, z) {
    y.on("start.zoom", function() {
      x(this, arguments).event(z).start();
    }).on("interrupt.zoom end.zoom", function() {
      x(this, arguments).event(z).end();
    }).tween("zoom", function() {
      var R = this, I = arguments, F = x(R, I).event(z), O = e.apply(R, I), X = w == null ? p(O) : typeof w == "function" ? w.apply(R, I) : w, ot = Math.max(O[1][0] - O[0][0], O[1][1] - O[0][1]), G = R.__zoom, nt = typeof S == "function" ? S.apply(R, I) : S, st = c(G.invert(X).concat(ot / G.k), nt.invert(X).concat(ot / nt.k));
      return function(Z) {
        if (Z === 1) Z = nt;
        else {
          var at = st(Z), $t = ot / at[2];
          Z = new vt($t, X[0] - at[0] * $t, X[1] - at[1] * $t);
        }
        F.zoom(null, Z);
      };
    });
  }
  function x(y, S, w) {
    return !w && y.__zooming || new $(y, S);
  }
  function $(y, S) {
    this.that = y, this.args = S, this.active = 0, this.sourceEvent = null, this.extent = e.apply(y, S), this.taps = 0;
  }
  $.prototype = {
    event: function(y) {
      return y && (this.sourceEvent = y), this;
    },
    start: function() {
      return ++this.active === 1 && (this.that.__zooming = this, this.emit("start")), this;
    },
    zoom: function(y, S) {
      return this.mouse && y !== "mouse" && (this.mouse[1] = S.invert(this.mouse[0])), this.touch0 && y !== "touch" && (this.touch0[1] = S.invert(this.touch0[0])), this.touch1 && y !== "touch" && (this.touch1[1] = S.invert(this.touch1[0])), this.that.__zoom = S, this.emit("zoom"), this;
    },
    end: function() {
      return --this.active === 0 && (delete this.that.__zooming, this.emit("end")), this;
    },
    emit: function(y) {
      var S = rt(this.that).datum();
      a.call(
        y,
        this.that,
        new ra(y, {
          sourceEvent: this.sourceEvent,
          target: m,
          transform: this.that.__zoom,
          dispatch: a
        }),
        S
      );
    }
  };
  function D(y, ...S) {
    if (!t.apply(this, arguments)) return;
    var w = x(this, S).event(y), z = this.__zoom, R = Math.max(o[0], Math.min(o[1], z.k * Math.pow(2, r.apply(this, arguments)))), I = mt(y);
    if (w.wheel)
      (w.mouse[0][0] !== I[0] || w.mouse[0][1] !== I[1]) && (w.mouse[1] = z.invert(w.mouse[0] = I)), clearTimeout(w.wheel);
    else {
      if (z.k === R) return;
      w.mouse = [I, z.invert(I)], te(this), w.start();
    }
    Dt(y), w.wheel = setTimeout(F, k), w.zoom("mouse", n(C(M(z, R), w.mouse[0], w.mouse[1]), w.extent, s));
    function F() {
      w.wheel = null, w.end();
    }
  }
  function K(y, ...S) {
    if (h || !t.apply(this, arguments)) return;
    var w = y.currentTarget, z = x(this, S, !0).event(y), R = rt(y.view).on("mousemove.zoom", X, !0).on("mouseup.zoom", ot, !0), I = mt(y, w), F = y.clientX, O = y.clientY;
    Dn(y.view), de(y), z.mouse = [I, this.__zoom.invert(I)], te(this), z.start();
    function X(G) {
      if (Dt(G), !z.moved) {
        var nt = G.clientX - F, st = G.clientY - O;
        z.moved = nt * nt + st * st > _;
      }
      z.event(G).zoom("mouse", n(C(z.that.__zoom, z.mouse[0] = mt(G, w), z.mouse[1]), z.extent, s));
    }
    function ot(G) {
      R.on("mousemove.zoom mouseup.zoom", null), Rn(G.view, z.moved), Dt(G), z.event(G).end();
    }
  }
  function H(y, ...S) {
    if (t.apply(this, arguments)) {
      var w = this.__zoom, z = mt(y.changedTouches ? y.changedTouches[0] : y, this), R = w.invert(z), I = w.k * (y.shiftKey ? 0.5 : 2), F = n(C(M(w, I), z, R), e.apply(this, S), s);
      Dt(y), u > 0 ? rt(this).transition().duration(u).call(T, F, z, y) : rt(this).call(m.transform, F, z, y);
    }
  }
  function q(y, ...S) {
    if (t.apply(this, arguments)) {
      var w = y.touches, z = w.length, R = x(this, S, y.changedTouches.length === z).event(y), I, F, O, X;
      for (de(y), F = 0; F < z; ++F)
        O = w[F], X = mt(O, this), X = [X, this.__zoom.invert(X), O.identifier], R.touch0 ? !R.touch1 && R.touch0[2] !== X[2] && (R.touch1 = X, R.taps = 0) : (R.touch0 = X, I = !0, R.taps = 1 + !!l);
      l && (l = clearTimeout(l)), I && (R.taps < 2 && (v = X[0], l = setTimeout(function() {
        l = null;
      }, d)), te(this), R.start());
    }
  }
  function Q(y, ...S) {
    if (this.__zooming) {
      var w = x(this, S).event(y), z = y.changedTouches, R = z.length, I, F, O, X;
      for (Dt(y), I = 0; I < R; ++I)
        F = z[I], O = mt(F, this), w.touch0 && w.touch0[2] === F.identifier ? w.touch0[0] = O : w.touch1 && w.touch1[2] === F.identifier && (w.touch1[0] = O);
      if (F = w.that.__zoom, w.touch1) {
        var ot = w.touch0[0], G = w.touch0[1], nt = w.touch1[0], st = w.touch1[1], Z = (Z = nt[0] - ot[0]) * Z + (Z = nt[1] - ot[1]) * Z, at = (at = st[0] - G[0]) * at + (at = st[1] - G[1]) * at;
        F = M(F, Math.sqrt(Z / at)), O = [(ot[0] + nt[0]) / 2, (ot[1] + nt[1]) / 2], X = [(G[0] + st[0]) / 2, (G[1] + st[1]) / 2];
      } else if (w.touch0) O = w.touch0[0], X = w.touch0[1];
      else return;
      w.zoom("touch", n(C(F, O, X), w.extent, s));
    }
  }
  function W(y, ...S) {
    if (this.__zooming) {
      var w = x(this, S).event(y), z = y.changedTouches, R = z.length, I, F;
      for (de(y), h && clearTimeout(h), h = setTimeout(function() {
        h = null;
      }, d), I = 0; I < R; ++I)
        F = z[I], w.touch0 && w.touch0[2] === F.identifier ? delete w.touch0 : w.touch1 && w.touch1[2] === F.identifier && delete w.touch1;
      if (w.touch1 && !w.touch0 && (w.touch0 = w.touch1, delete w.touch1), w.touch0) w.touch0[1] = this.__zoom.invert(w.touch0[0]);
      else if (w.end(), w.taps === 2 && (F = mt(F, this), Math.hypot(v[0] - F[0], v[1] - F[1]) < f)) {
        var O = rt(this).on("dblclick.zoom");
        O && O.apply(this, arguments);
      }
    }
  }
  return m.wheelDelta = function(y) {
    return arguments.length ? (r = typeof y == "function" ? y : Qt(+y), m) : r;
  }, m.filter = function(y) {
    return arguments.length ? (t = typeof y == "function" ? y : Qt(!!y), m) : t;
  }, m.touchable = function(y) {
    return arguments.length ? (i = typeof y == "function" ? y : Qt(!!y), m) : i;
  }, m.extent = function(y) {
    return arguments.length ? (e = typeof y == "function" ? y : Qt([[+y[0][0], +y[0][1]], [+y[1][0], +y[1][1]]]), m) : e;
  }, m.scaleExtent = function(y) {
    return arguments.length ? (o[0] = +y[0], o[1] = +y[1], m) : [o[0], o[1]];
  }, m.translateExtent = function(y) {
    return arguments.length ? (s[0][0] = +y[0][0], s[1][0] = +y[1][0], s[0][1] = +y[0][1], s[1][1] = +y[1][1], m) : [[s[0][0], s[0][1]], [s[1][0], s[1][1]]];
  }, m.constrain = function(y) {
    return arguments.length ? (n = y, m) : n;
  }, m.duration = function(y) {
    return arguments.length ? (u = +y, m) : u;
  }, m.interpolate = function(y) {
    return arguments.length ? (c = y, m) : c;
  }, m.on = function() {
    var y = a.on.apply(a, arguments);
    return y === a ? m : y;
  }, m.clickDistance = function(y) {
    return arguments.length ? (_ = (y = +y) * y, m) : Math.sqrt(_);
  }, m.tapDistance = function(y) {
    return arguments.length ? (f = +y, m) : f;
  }, m;
}
function fn(t, e) {
  return t._kind !== "entity" ? t.color : e === "community" ? t.communityColor : t.typeColor;
}
const ye = [0.05, 6], la = {
  seed: 42,
  linkDistance: 200,
  linkStrength: 0.2,
  chargeStrength: -3e3,
  collideRadius: 50,
  centerStrength: 0.05,
  isolatedRadius: 100,
  isolatedStrength: 0.15,
  alphaDecay: 0.05
}, hn = 0.22, fa = 60, gn = "#7c5cff", pe = "#a78bfa", ha = 0.35, dn = 0.85, yn = 0.4, pn = 1.2, mn = "#8b94a8", ga = "#5b6478", me = 1.5, ve = 0.45;
function da(t, e, n = {}) {
  const r = { ...la, ...e.meta.force_settings ?? {} }, i = na(r.seed / 4294967295), o = t.clientWidth || 800, s = t.clientHeight || 600, u = rt(t).append("svg").attr("class", "grail-viz-svg").attr("width", "100%").attr("height", "100%").attr("viewBox", `0 0 ${o} ${s}`).style("display", "block").style("cursor", "grab"), c = u.append("g").attr("class", "grail-viz-root"), a = c.append("g").attr("class", "links"), l = c.append("g").attr("class", "nodes"), v = e.nodes.map((g) => {
    const b = i() * Math.PI * 2, E = 200 + i() * 200;
    return {
      key: g.key,
      attrs: g.attributes,
      x: o / 2 + Math.cos(b) * E,
      y: s / 2 + Math.sin(b) * E,
      isolated: !1
    };
  }), h = new Map(v.map((g) => [g.key, g])), d = /* @__PURE__ */ new Map();
  for (const g of e.edges) {
    const b = g.source < g.target ? g.source : g.target, E = g.source < g.target ? g.target : g.source, A = `${b}|${E}`;
    d.set(A, (d.get(A) ?? 0) + 1);
  }
  const k = /* @__PURE__ */ new Map(), _ = e.edges.map((g) => {
    const b = g.source < g.target ? g.source : g.target, E = g.source < g.target ? g.target : g.source, A = `${b}|${E}`, L = d.get(A) ?? 1, P = k.get(A) ?? 0;
    k.set(A, P + 1);
    const V = L > 1 ? -hn + P * 2 * hn / (L - 1) : 0;
    return {
      key: g.key,
      source: h.get(g.source) ?? g.source,
      target: h.get(g.target) ?? g.target,
      attrs: g.attributes,
      curveStrength: V,
      isSelfLoop: g.source === g.target
    };
  }), f = {
    visibleKinds: new Set(
      e.meta.default_visible_kinds.length > 0 ? e.meta.default_visible_kinds : ["entity"]
    ),
    visibleEdgeKinds: new Set(
      e.meta.default_visible_edge_kinds.length > 0 ? e.meta.default_visible_edge_kinds : ["RELATED"]
    ),
    typeFilter: /* @__PURE__ */ new Set(),
    colorMode: n.colorMode ?? "community",
    selectedNode: null,
    selectedEdge: null,
    hoveredNode: null,
    hoveredEdge: null
  }, m = /* @__PURE__ */ new Set(), M = () => m.forEach((g) => g({ ...f })), C = (g) => f.visibleKinds.has(g.attrs._kind) ? g.attrs._kind === "entity" && f.typeFilter.size > 0 ? f.typeFilter.has(g.attrs._type ?? "") : !0 : !1, p = (g) => {
    if (!f.visibleEdgeKinds.has(g.attrs._kind)) return !1;
    const b = typeof g.source == "string" ? h.get(g.source) : g.source, E = typeof g.target == "string" ? h.get(g.target) : g.target;
    return !b || !E ? !1 : C(b) && C(E);
  }, T = () => {
    const g = new Set(f.visibleEdgeKinds);
    return f.visibleKinds.has("chunk") && f.visibleKinds.has("document") && g.delete("MENTIONS"), g;
  }, x = () => {
    const g = /* @__PURE__ */ new Set();
    f.visibleKinds.has("entity") && g.add("RELATED"), f.visibleKinds.has("entity") && f.visibleKinds.has("community") && g.add("IN_COMMUNITY"), f.visibleKinds.has("chunk") && f.visibleKinds.has("document") && g.add("PART_OF"), f.visibleKinds.has("chunk") && f.visibleKinds.has("entity") && g.add("HAS_ENTITY"), f.visibleKinds.has("community") && f.visibleKinds.has("finding") && g.add("HAS_FINDING"), f.visibleKinds.has("document") && f.visibleKinds.has("entity") && !f.visibleKinds.has("chunk") && g.add("MENTIONS"), f.visibleEdgeKinds = g;
  };
  x();
  const $ = () => {
    const g = T(), b = /* @__PURE__ */ new Set();
    for (const E of _) {
      if (!g.has(E.attrs._kind)) continue;
      const A = typeof E.source == "string" ? E.source : E.source.key, L = typeof E.target == "string" ? E.target : E.target.key;
      b.add(A), b.add(L);
    }
    for (const E of v)
      E.isolated = !b.has(E.key);
  };
  $();
  const D = qs(_).id((g) => g.key).distance(r.linkDistance).strength((g) => pa(g.attrs._kind, r.linkStrength)), K = js().strength(
    (g) => g.isolated ? -Math.abs(r.chargeStrength) / 6 : ya(g.attrs._kind, r.chargeStrength)
  ).distanceMin(20).distanceMax(900).theta(0.8), H = Xs().radius((g) => (g.attrs.size ?? 6) + 8).strength(0.3).iterations(4), q = ks(o / 2, s / 2).strength(r.centerStrength), Q = Math.min(o, s) * 0.42, W = un(Q, o / 2, s / 2).strength((g) => g.attrs._kind === "document" ? 0.18 : 0), y = un(r.isolatedRadius, o / 2, s / 2).strength((g) => g.isolated ? r.isolatedStrength : 5e-3), S = Js(v).force("link", D).force("charge", K).force("center", q).force("collide", H).force("docRing", W).force("isolated", y).velocityDecay(0.4).alphaDecay(r.alphaDecay).alphaMin(1e-3);
  let w = 1;
  const z = ca().scaleExtent(ye).on("zoom", (g) => {
    c.attr("transform", g.transform.toString());
    const b = w;
    w = g.transform.k;
    const E = b >= me != w >= me, A = b >= ve != w >= ve;
    (E || A) && O();
  });
  u.call(z);
  const R = a.selectAll("g.link").data(_, (g) => g.key).join((g) => {
    const b = g.append("g").attr("class", "link");
    return b.append("path").attr("fill", "none").attr("stroke", (E) => _n(E.attrs.color)).attr("stroke-opacity", dn).attr(
      "stroke-width",
      (E) => Math.max(pn, E.attrs.size ?? 1)
    ).attr("stroke-linecap", "round").attr("data-key", (E) => E.key).style("cursor", "pointer").on("click", (E, A) => {
      E.stopPropagation(), nt(A.key);
    }), b.filter((E) => _e(E.attrs.label, E.attrs._kind)).each(
      function() {
        const E = rt(this).append("g").attr("class", "link-label").style("opacity", 0).style("pointer-events", "none");
        E.append("rect").attr("rx", 4).attr("ry", 4), E.append("text").attr("text-anchor", "middle").attr("dominant-baseline", "middle");
      }
    ), b;
  }), I = l.selectAll("g.node").data(v, (g) => g.key).join((g) => {
    const b = g.append("g").attr("class", "node").style("cursor", "pointer");
    return b.append("circle").attr("r", (E) => Math.max(3, E.attrs.size ?? 6)).attr("fill", (E) => fn(E.attrs, f.colorMode)).attr("stroke", "#1b2030").attr("stroke-width", 1), b.append("text").attr("dx", (E) => Math.max(3, E.attrs.size ?? 6) + 4).attr("dy", "0.32em").attr("font-size", 11).attr("fill", "currentColor").style("pointer-events", "none").text((E) => vn(E.attrs.label, 28)), b.call(Wn(S)), b.on("click", (E, A) => {
      E.stopPropagation(), G(A.key);
    }), b.on("mouseenter", (E, A) => st(A.key)), b.on("mouseleave", () => st(null)), b;
  });
  u.on("click", () => {
    var g;
    f.selectedNode = null, f.selectedEdge = null, O(), M(), (g = n.onSelectionChange) == null || g.call(n, { node: null, edge: null, edgeEndpoints: null });
  }), S.on("tick", () => {
    R.each(function(g) {
      const E = rt(this).select("path"), A = typeof g.source == "object" ? g.source : h.get(g.source), L = typeof g.target == "object" ? g.target : h.get(g.target);
      if (!A || !L || A.x == null || A.y == null || L.x == null || L.y == null) return;
      let P, V = 0, N = 0, B = 0;
      if (g.isSelfLoop) {
        const ut = A.y - 56 - 8;
        P = `M${A.x},${A.y} C${A.x - 36},${ut} ${A.x + 36},${ut} ${A.x},${A.y}`, V = A.x, N = ut;
      } else {
        const U = L.x - A.x, gt = L.y - A.y, ut = Math.sqrt(U * U + gt * gt) || 1, le = (A.x + L.x) / 2, bt = (A.y + L.y) / 2, Bt = -gt / ut, Zn = U / ut, Oe = ut * g.curveStrength, Ke = le + Bt * Oe, He = bt + Zn * Oe;
        P = `M${A.x},${A.y} Q${Ke},${He} ${L.x},${L.y}`, V = 0.25 * A.x + 0.5 * Ke + 0.25 * L.x, N = 0.25 * A.y + 0.5 * He + 0.25 * L.y, B = Math.atan2(gt, U) * 180 / Math.PI, (B > 90 || B < -90) && (B -= 180);
      }
      E.attr("d", P);
      const J = this.querySelector(".link-label");
      J && J.setAttribute(
        "transform",
        `translate(${V},${N}) rotate(${B})`
      );
    }), I.attr("transform", (g) => `translate(${g.x ?? 0},${g.y ?? 0})`);
  });
  let F = !1;
  S.on("end", () => {
    F || (F = !0, at());
  });
  function O() {
    const g = T(), b = f.selectedNode ?? f.hoveredNode, E = f.selectedEdge ?? f.hoveredEdge, A = /* @__PURE__ */ new Set(), L = /* @__PURE__ */ new Set();
    if (b) {
      L.add(b);
      for (const N of _) {
        const B = typeof N.source == "string" ? N.source : N.source.key, J = typeof N.target == "string" ? N.target : N.target.key;
        (B === b || J === b) && g.has(N.attrs._kind) && (A.add(N.key), L.add(B), L.add(J));
      }
    }
    if (E) {
      const N = _.find((B) => B.key === E);
      if (N) {
        A.add(N.key);
        const B = typeof N.source == "string" ? N.source : N.source.key, J = typeof N.target == "string" ? N.target : N.target.key;
        L.add(B), L.add(J);
      }
    }
    I.style("display", (N) => C(N) ? "" : "none").style(
      "opacity",
      (N) => (b || E) && !L.has(N.key) ? yn : 1
    ), I.select("circle").attr("fill", (N) => fn(N.attrs, f.colorMode)).attr(
      "stroke",
      (N) => N.key === f.selectedNode ? gn : N.key === f.hoveredNode ? pe : "#1b2030"
    ).attr(
      "stroke-width",
      (N) => N.key === f.selectedNode || N.key === f.hoveredNode ? 2.5 : 1
    ), R.style(
      "display",
      (N) => g.has(N.attrs._kind) && p(N) ? "" : "none"
    ).select("path").attr("stroke", (N) => N.key === f.selectedEdge ? gn : N.key === f.hoveredEdge || b && A.has(N.key) ? pe : f.colorMode === "community" && N.attrs._kind === "RELATED" && X(N) ? ot(N) : _n(N.attrs.color)).attr("stroke-opacity", (N) => N.key === f.selectedEdge || N.key === f.hoveredEdge ? 1 : b ? A.has(N.key) ? 0.95 : ha : f.colorMode === "community" && N.attrs._kind === "RELATED" && X(N) ? 0.7 : dn).attr("stroke-width", (N) => {
      const B = Math.max(pn, N.attrs.size ?? 1);
      return N.key === f.selectedEdge || N.key === f.hoveredEdge ? B + 1.4 : B;
    });
    const P = w >= me;
    R.select(".link-label").style("opacity", (N) => N.key === f.selectedEdge ? 1 : N.key === f.hoveredEdge ? 0.95 : !P || !_e(N.attrs.label, N.attrs._kind) ? 0 : b ? A.has(N.key) ? 0.95 : 0.45 : 0.85), R.select(".link-label").each(function(N) {
      var Bt;
      if (!(N.key === f.selectedEdge || N.key === f.hoveredEdge || P && _e(N.attrs.label, N.attrs._kind))) return;
      const U = rt(this), gt = U.select("text"), ut = U.select("rect"), le = N.attrs.label ?? N.attrs._kind;
      gt.text(vn(le, fa)).attr("fill", "currentColor").attr("font-size", 10);
      const bt = (Bt = gt.node()) == null ? void 0 : Bt.getBBox();
      bt && ut.attr("x", -bt.width / 2 - 6).attr("y", -bt.height / 2 - 3).attr("width", bt.width + 12).attr("height", bt.height + 6).attr("fill", "rgba(19, 23, 34, 0.92)");
    });
    const V = w >= ve;
    I.select("text").style("opacity", (N) => V ? (b || E) && !L.has(N.key) ? yn : 1 : 0);
  }
  function X(g) {
    const b = typeof g.source == "string" ? h.get(g.source) : g.source, E = typeof g.target == "string" ? h.get(g.target) : g.target;
    return !b || !E ? !1 : b.attrs._kind === "entity" && E.attrs._kind === "entity" && !!b.attrs._community && b.attrs._community === E.attrs._community;
  }
  function ot(g) {
    const b = typeof g.source == "string" ? h.get(g.source) : g.source;
    return (b == null ? void 0 : b.attrs.communityColor) ?? "#666c79";
  }
  function G(g) {
    var E;
    f.selectedNode = g, f.selectedEdge = null, $t(g), O(), M();
    const b = h.get(g);
    (E = n.onSelectionChange) == null || E.call(n, { node: (b == null ? void 0 : b.attrs) ?? null, edge: null, edgeEndpoints: null });
  }
  function nt(g) {
    var L, P;
    f.selectedNode = null, f.selectedEdge = g;
    const b = _.find((V) => V.key === g);
    if (O(), M(), !b) {
      (L = n.onSelectionChange) == null || L.call(n, { node: null, edge: null, edgeEndpoints: null });
      return;
    }
    const E = typeof b.source == "string" ? h.get(b.source) : b.source, A = typeof b.target == "string" ? h.get(b.target) : b.target;
    (P = n.onSelectionChange) == null || P.call(n, {
      node: null,
      edge: b.attrs,
      edgeEndpoints: E && A ? { source: E.attrs, target: A.attrs } : null
    }), E && A && E.x != null && E.y != null && A.x != null && A.y != null && Z(
      Math.min(E.x, A.x),
      Math.min(E.y, A.y),
      Math.max(E.x, A.x),
      Math.max(E.y, A.y),
      120
    );
  }
  function st(g) {
    f.hoveredNode = g, f.hoveredEdge = null, O();
  }
  function Z(g, b, E, A, L = 80) {
    const P = t.clientWidth || o, V = t.clientHeight || s, N = Math.max(1, E - g) + L * 2, B = Math.max(1, A - b) + L * 2, J = Math.max(
      ye[0],
      Math.min(ye[1], 0.9 * Math.min(P / N, V / B))
    ), U = (g + E) / 2, gt = (b + A) / 2, ut = Fe.translate(P / 2 - U * J, V / 2 - gt * J).scale(J);
    u.transition().duration(650).ease(Gn).call(
      z.transform,
      ut
    );
  }
  function at() {
    const g = v.filter((P) => C(P) && P.x != null && P.y != null);
    if (g.length === 0) return;
    let b = 1 / 0, E = 1 / 0, A = -1 / 0, L = -1 / 0;
    for (const P of g) {
      const V = Math.max(3, P.attrs.size ?? 6);
      b = Math.min(b, (P.x ?? 0) - V), E = Math.min(E, (P.y ?? 0) - V), A = Math.max(A, (P.x ?? 0) + V), L = Math.max(L, (P.y ?? 0) + V);
    }
    Z(b, E, A, L, 60);
  }
  function $t(g) {
    const b = h.get(g);
    if (!b || b.x == null || b.y == null) return;
    const E = T();
    let A = b.x, L = b.y, P = b.x, V = b.y;
    for (const N of _) {
      if (!E.has(N.attrs._kind)) continue;
      const B = typeof N.source == "string" ? N.source : N.source.key, J = typeof N.target == "string" ? N.target : N.target.key;
      if (B !== g && J !== g) continue;
      const U = h.get(B === g ? J : B);
      !U || U.x == null || U.y == null || (A = Math.min(A, U.x), L = Math.min(L, U.y), P = Math.max(P, U.x), V = Math.max(V, U.y));
    }
    Z(A, L, P, V, 100);
  }
  function Wn(g) {
    return Ki().on("start", (b) => {
      b.active || g.velocityDecay(0.7).alphaTarget(0.1).restart(), b.subject.fx = b.subject.x ?? 0, b.subject.fy = b.subject.y ?? 0;
    }).on("drag", (b) => {
      b.subject.fx = b.x, b.subject.fy = b.y;
    }).on("end", (b) => {
      b.active || g.velocityDecay(0.4).alphaTarget(0);
    });
  }
  const Qn = {
    payload: e,
    destroy() {
      S.stop(), u.remove(), m.clear();
    },
    relayout() {
      S.alpha(1).restart(), F = !1;
    },
    setKindVisible(g, b) {
      b ? f.visibleKinds.add(g) : f.visibleKinds.delete(g), x(), $(), S.alpha(0.5).restart(), O(), M();
    },
    setTypeFilter(g) {
      f.typeFilter = new Set(g), $(), S.alpha(0.3).restart(), O(), M();
    },
    setColorMode(g) {
      f.colorMode = g, O(), M();
    },
    focusNode(g) {
      $t(g);
    },
    searchNodes(g, b = 12) {
      const E = g.trim().toLowerCase();
      if (!E) return [];
      const A = [];
      for (const L of v)
        if (L.attrs._kind === "entity" && C(L) && L.attrs.label.toLowerCase().includes(E) && (A.push({ key: L.key, attributes: L.attrs }), A.length >= b))
          break;
      return A;
    },
    getState() {
      return { ...f };
    },
    subscribe(g) {
      return m.add(g), () => m.delete(g);
    }
  };
  return O(), S.alpha(1).restart(), Qn;
}
function ya(t, e) {
  switch (t) {
    case "community":
      return -Math.abs(e) * 0.28;
    case "document":
      return -Math.abs(e) * 0.7;
    case "chunk":
      return -Math.abs(e) * 0.12;
    case "finding":
      return -Math.abs(e) * 0.08;
    case "entity":
    default:
      return e;
  }
}
function pa(t, e) {
  switch (t) {
    case "IN_COMMUNITY":
      return e * 0.25;
    case "HAS_FINDING":
      return e * 1.6;
    case "HAS_ENTITY":
      return e * 0.6;
    case "PART_OF":
      return e * 0.8;
    case "MENTIONS":
      return e * 0.4;
    case "RELATED":
    default:
      return e * 1.2;
  }
}
function vn(t, e) {
  return t ? t.length > e ? t.slice(0, e - 1) + "…" : t : "";
}
function _n(t) {
  return !t || t.toLowerCase() === ga ? mn : t;
}
function _e(t, e) {
  return t && t.trim().length > 0 ? !0 : e === "RELATED";
}
const ma = {
  entity: "Entities",
  document: "Documents",
  chunk: "Chunks",
  community: "Communities",
  finding: "Findings"
}, va = ["entity", "community", "document", "chunk", "finding"];
function _a(t, e) {
  var T;
  const n = e.payload.meta;
  t.classList.add("grail-viz-sidebar"), t.innerHTML = `
    <section class="gv-section gv-stats">
      <h3>Stats</h3>
      <dl class="gv-stats-grid"></dl>
    </section>

    <section class="gv-section">
      <h3>Search</h3>
      <input class="gv-search-input" type="search" placeholder="Find an entity…" autocomplete="off" />
      <ul class="gv-search-results"></ul>
    </section>

    <section class="gv-section">
      <h3>Layers</h3>
      <div class="gv-layers"></div>
    </section>

    <section class="gv-section">
      <h3>Color entities by</h3>
      <div class="gv-color-toggle">
        <button data-mode="community" class="gv-pill">Community</button>
        <button data-mode="type" class="gv-pill">Type</button>
      </div>
    </section>

    <section class="gv-section gv-types">
      <h3>Entity types</h3>
      <ul class="gv-type-list"></ul>
    </section>

    <section class="gv-section gv-selected">
      <h3>Selected</h3>
      <div class="gv-detail">
        <p class="gv-detail-empty">Click a node or edge to see details.</p>
      </div>
    </section>
  `;
  const r = t.querySelector(".gv-stats-grid"), i = [
    ["Entities", n.n_entities],
    ["Relationships", n.n_relationships],
    ["Communities", n.n_communities],
    ["Documents", n.n_documents],
    ["Chunks", n.n_chunks],
    ["Findings", n.n_findings]
  ];
  r.innerHTML = i.map(([x, $]) => `<dt>${x}</dt><dd>${$.toLocaleString()}</dd>`).join("");
  const o = t.querySelector(".gv-layers");
  o.innerHTML = va.map((x) => {
    var K;
    const $ = ((K = n.kind_counts) == null ? void 0 : K[x]) ?? 0, D = e.getState().visibleKinds.has(x);
    return `
      <label class="gv-layer">
        <input type="checkbox" data-kind="${x}" ${D ? "checked" : ""} ${$ === 0 ? "disabled" : ""} />
        <span class="gv-layer-swatch" data-kind="${x}"></span>
        <span class="gv-layer-name">${ma[x]}</span>
        <span class="gv-layer-count">${$.toLocaleString()}</span>
      </label>
    `;
  }).join("");
  for (const x of t.querySelectorAll(".gv-layer-swatch")) {
    const $ = x.dataset.kind ?? "";
    x.style.background = ((T = n.kind_palette) == null ? void 0 : T[$]) ?? "#7c5cff";
  }
  for (const x of t.querySelectorAll('.gv-layer input[type="checkbox"]'))
    x.addEventListener("change", () => {
      e.setKindVisible(x.dataset.kind, x.checked);
    });
  const s = t.querySelectorAll(".gv-color-toggle button"), u = () => {
    const x = e.getState().colorMode;
    for (const $ of s)
      $.classList.toggle("active", $.dataset.mode === x);
  };
  for (const x of s)
    x.addEventListener("click", () => {
      e.setColorMode(x.dataset.mode);
    });
  u();
  const c = t.querySelector(".gv-type-list"), a = Object.entries(n.type_counts ?? {}).sort((x, $) => $[1] - x[1]);
  a.length === 0 ? c.innerHTML = '<li class="gv-empty">No typed entities</li>' : c.innerHTML = a.map(
    ([x, $]) => {
      var D;
      return `
        <li class="gv-type" data-type="${xn(x)}">
          <span class="gv-type-swatch" style="background:${((D = n.type_palette) == null ? void 0 : D[x]) ?? "#7c5cff"}"></span>
          <span class="gv-type-name">${Y(x)}</span>
          <span class="gv-type-count">${$.toLocaleString()}</span>
        </li>
      `;
    }
  ).join("");
  const l = /* @__PURE__ */ new Set();
  for (const x of c.querySelectorAll("li.gv-type"))
    x.addEventListener("click", () => {
      const $ = x.dataset.type ?? "";
      l.has($) ? l.delete($) : l.add($);
      for (const D of c.querySelectorAll("li.gv-type"))
        D.classList.toggle("active", l.has(D.dataset.type ?? ""));
      e.setTypeFilter(l);
    });
  const v = t.querySelector(".gv-search-input"), h = t.querySelector(".gv-search-results");
  let d;
  v.addEventListener("input", () => {
    d != null && window.clearTimeout(d), d = window.setTimeout(() => {
      const x = v.value, $ = e.searchNodes(x, 10);
      if ($.length === 0) {
        h.innerHTML = x ? '<li class="gv-empty">No matches</li>' : "";
        return;
      }
      h.innerHTML = $.map(
        (D) => `
          <li class="gv-search-hit" data-key="${xn(D.key)}">
            <span class="gv-hit-swatch" style="background:${D.attributes.communityColor}"></span>
            <span class="gv-hit-name">${Y(D.attributes.label)}</span>
            ${D.attributes._type ? `<span class="gv-hit-type">${Y(D.attributes._type)}</span>` : ""}
          </li>
        `
      ).join("");
      for (const D of h.querySelectorAll("li.gv-search-hit"))
        D.addEventListener("click", () => {
          const K = D.dataset.key ?? "";
          e.focusNode(K);
        });
    }, 80);
  });
  const k = t.querySelector(".gv-detail"), _ = (x) => {
    if (x.node) {
      k.innerHTML = xa(x.node);
      return;
    }
    if (x.edge) {
      k.innerHTML = wa(x.edge, x.edgeEndpoints ?? null);
      return;
    }
    k.innerHTML = '<p class="gv-detail-empty">Click a node or edge to see details.</p>';
  };
  let f = null, m = null;
  const M = new Map(e.payload.nodes.map((x) => [x.key, x.attributes])), C = new Map(e.payload.edges.map((x) => [x.key, x])), p = e.subscribe((x) => {
    if (x.selectedNode !== f || x.selectedEdge !== m)
      if (f = x.selectedNode, m = x.selectedEdge, x.selectedNode) {
        const $ = M.get(x.selectedNode);
        _({ node: $ ?? null, edge: null });
      } else if (x.selectedEdge) {
        const $ = C.get(x.selectedEdge);
        if ($) {
          const D = M.get($.source), K = M.get($.target);
          _({
            node: null,
            edge: $.attributes,
            edgeEndpoints: D && K ? { source: D, target: K } : null
          });
        } else
          _({ node: null, edge: null });
      } else
        _({ node: null, edge: null });
    u();
  });
  return {
    destroy() {
      p(), t.innerHTML = "", t.classList.remove("grail-viz-sidebar");
    }
  };
}
function xa(t) {
  switch (t._kind) {
    case "entity":
      return `
        ${kt(t._type ?? "ENTITY", t.typeColor)}
        ${t._community ? kt("Community " + t._community, t.communityColor, "ghost") : ""}
        <h4>${Y(t.label)}</h4>
        ${ct("Degree", String(t._degree ?? 0))}
        ${t._description ? Lt("Description", Y(t._description)) : ""}
        ${ba(t._documents)}
      `;
    case "document":
      return `
        ${kt("DOCUMENT", t.color)}
        <h4>${Y(t._title ?? t.label)}</h4>
        ${t._path ? ct("Path", Y(t._path)) : ""}
        ${ct("Chunks", String(t._n_text_units ?? 0))}
      `;
    case "chunk":
      return `
        ${kt("CHUNK", t.color)}
        <h4>${Y(t.label)}</h4>
        ${ct("Tokens", String(t._n_tokens ?? 0))}
        ${t._text ? Lt("Preview", Y(t._text)) : ""}
      `;
    case "community":
      return `
        ${kt("COMMUNITY", t.color)}
        <h4>${Y(t._title ?? t.label)}</h4>
        ${ct("Level", String(t._level ?? 0))}
        ${ct("Members", String(t._size ?? 0))}
        ${ct("Rank", (t._rank ?? 0).toFixed(2))}
        ${ct("Findings", String(t._n_findings ?? 0))}
        ${t._summary ? Lt("Summary", Y(t._summary)) : ""}
      `;
    case "finding":
      return `
        ${kt("FINDING", t.color)}
        <h4>${Y(t._summary ?? t.label)}</h4>
        ${t._community_id ? ct("Community", Y(t._community_id)) : ""}
        ${t._explanation ? Lt("Explanation", Y(t._explanation)) : ""}
      `;
  }
}
function wa(t, e) {
  const n = e ? `<p class="gv-edge-triple">
         <span>${Y(e.source.label)}</span>
         <strong>${Y(t.label ?? t._kind)}</strong>
         <span>${Y(e.target.label)}</span>
       </p>` : "";
  return `
    ${kt(t._kind, t.color)}
    <h4>Relationship</h4>
    ${n}
    ${t._description ? Lt("Description", Y(t._description)) : ""}
    ${ct("Weight", (t._weight ?? 0).toFixed(2))}
    ${ct("Rank", (t._rank ?? 0).toFixed(2))}
  `;
}
function kt(t, e, n = "solid") {
  return n === "ghost" ? `<span class="gv-badge gv-badge-ghost" style="color:${e};border-color:${e}">${Y(t)}</span>` : `<span class="gv-badge" style="background:${e}">${Y(t)}</span>`;
}
function ct(t, e) {
  return `<p class="gv-row"><span>${Y(t)}</span><span>${e}</span></p>`;
}
function Lt(t, e) {
  return `<div class="gv-section-block"><h5>${Y(t)}</h5><p>${e}</p></div>`;
}
function ba(t) {
  return !t || t.length === 0 ? "" : `
    <div class="gv-section-block">
      <h5>Documents</h5>
      <ul class="gv-doc-list">
        ${t.map((e) => `<li>${Y(e)}</li>`).join("")}
      </ul>
    </div>
  `;
}
function Y(t) {
  return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function xn(t) {
  return Y(t).replace(/'/g, "&#39;");
}
function ka(t, e, n, r = {}) {
  const i = da(t, n, r), o = _a(e, i);
  return {
    renderer: i,
    destroy() {
      o.destroy(), i.destroy();
    }
  };
}
export {
  da as createRenderer,
  ka as mount,
  _a as mountSidebar
};
//# sourceMappingURL=grail-viz.es.js.map
