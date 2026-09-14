/* ============================================================
   Cartube — tương tác
   Không phụ thuộc thư viện. Nạp cuối <body> bằng <script defer>.
   ============================================================ */
(function () {
  'use strict';

  /* ---------- 1. Viền header khi cuộn ---------- */
  var header = document.querySelector('.header');
  function onScroll() {
    if (header) header.classList.toggle('is-scrolled', window.scrollY > 8);
    highlightFeature();
  }
  window.addEventListener('scroll', onScroll, { passive: true });

  /* ---------- 2. Hiện dần khi cuộn tới ----------
     Quan trọng: luôn có lớp dự phòng. Nếu IntersectionObserver bị
     chặn (tab nền, iframe ẩn, khi xuất PDF) thì sau 1,3s hiện thẳng,
     không bao giờ để trang trắng.                                    */
  var reveals = [].slice.call(document.querySelectorAll('[data-reveal]'));
  function revealAll() { reveals.forEach(function (el) { el.classList.add('is-in'); }); }

  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add('is-in');
        io.unobserve(e.target);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.04 });
    reveals.forEach(function (el) { io.observe(el); });
  }
  setTimeout(revealAll, 1300);

  /* ---------- 3. Số liệu đếm lên ----------
     Đặt data-count="42000" data-suffix="+" (tuỳ chọn data-decimals="1")  */
  var counters = [].slice.call(document.querySelectorAll('[data-count]'));
  function runCounters() {
    var start = performance.now(), dur = 1400;
    function tick(now) {
      var raw = Math.min(1, (now - start) / dur);
      var t = 1 - Math.pow(1 - raw, 3);           // ease-out cubic
      counters.forEach(function (el) {
        var target = parseFloat(el.dataset.count);
        var dec = parseInt(el.dataset.decimals || '0', 10);
        var val = target * t;
        var text = dec
          ? val.toFixed(dec).replace('.', ',')
          : Math.round(val).toLocaleString('vi-VN');
        el.textContent = (el.dataset.prefix || '') + text + (el.dataset.suffix || '');
      });
      if (raw < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
  if (counters.length) {
    runCounters();
    setTimeout(function () {                       // dự phòng khi rAF bị chặn
      counters.forEach(function (el) {
        var dec = parseInt(el.dataset.decimals || '0', 10);
        var target = parseFloat(el.dataset.count);
        var text = dec ? target.toFixed(dec).replace('.', ',') : target.toLocaleString('vi-VN');
        el.textContent = (el.dataset.prefix || '') + text + (el.dataset.suffix || '');
      });
    }, 1300);
  }

  /* ---------- 4. Màn hình xe ngả theo con trỏ ---------- */
  var tilt = document.querySelector('.tilt');
  if (tilt && window.matchMedia('(pointer:fine)').matches) {
    window.addEventListener('mousemove', function (e) {
      var r = tilt.getBoundingClientRect();
      var dx = (e.clientX - (r.left + r.width / 2)) / r.width;
      var dy = (e.clientY - (r.top + r.height / 2)) / r.height;
      var inner = tilt.querySelector('.tilt__inner');
      if (inner) {
        inner.style.transform =
          'rotate(-2.4deg) rotateY(' + (dx * 7).toFixed(2) + 'deg) rotateX(' + (-dy * 5).toFixed(2) + 'deg)';
      }
    }, { passive: true });
  }

  /* ---------- 5. Số mục 01/02/03 đổi theo vị trí cuộn ---------- */
  var featureEls = [].slice.call(document.querySelectorAll('.feature'));
  var featureNum = document.querySelector('.features__num');
  function highlightFeature() {
    if (!featureEls.length || !featureNum) return;
    var mid = window.innerHeight * 0.42, best = 0, bestD = Infinity;
    featureEls.forEach(function (n, i) {
      var r = n.getBoundingClientRect();
      var d = Math.abs(r.top + r.height / 2 - mid);
      if (d < bestD) { bestD = d; best = i; }
    });
    featureEls.forEach(function (n, i) { n.classList.toggle('is-active', i === best); });
    featureNum.textContent = featureEls[best].dataset.num || '01';
  }
  highlightFeature();

  /* ---------- 6. Câu hỏi thường gặp ---------- */
  document.querySelectorAll('.faq__q').forEach(function (q) {
    q.addEventListener('click', function () {
      var item = q.parentElement;
      var open = item.classList.contains('is-open');
      document.querySelectorAll('.faq').forEach(function (f) { f.classList.remove('is-open'); });
      if (!open) item.classList.add('is-open');
    });
  });

  /* ---------- 7. Luồng mua key — nối thẳng vào máy chủ ----------
     Máy chủ là nguồn sự thật duy nhất: giá, mã đơn, và key đều do nó cấp.
     Trình duyệt KHÔNG bao giờ tự sinh key.                                */

  var API = '';
  var LS_ORDER = 'ct_order';

  /* ================== VI SAO PHAI BOC localStorage ==================
     Truy cap localStorage NEM LOI, khong phai tra null, khi trinh duyet chan
     luu tru: Safari duyet rieng tu, Chrome dat "chan tat ca cookie", cac trinh
     duyet chu trong rieng tu, va webview trong Zalo/Facebook.

     Truoc day ba cho goi thang. Mot cau getItem nem loi la chet ca doan khoi
     tao con lai cua trang mua key - nguoi dung thay trang nua voi, bam gi cung
     khong an, va thuong ke lai la "loi cookie".

     Boc lai thi mat tinh nang nho (khong nho don cu) nhung trang van chay. */
  var kho = {
    doc: function (k) {
      try { return localStorage.getItem(k); } catch (e) { return null; }
    },
    ghi: function (k, v) {
      try { localStorage.setItem(k, v); return true; } catch (e) { return false; }
    },
    xoa: function (k) {
      try { localStorage.removeItem(k); return true; } catch (e) { return false; }
    }
  };

  function money(n) { return Number(n).toLocaleString('vi-VN') + 'đ'; }

  function api(path, body) {
    return fetch(API + path, body ? {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    } : {}).then(function (r) {
      return r.json().then(function (j) {
        if (!j.ok) { throw new Error(j.error || 'loi_khong_ro'); }
        return j;
      });
    });
  }

  /* Lời nhắn tiếng Việt cho mã lỗi của máy chủ. Máy chủ trả mã, không trả câu —
     câu chữ là việc của trang.                                             */
  var ERRS = {
    plan_not_found:  'Gói này không còn bán. Tải lại trang giúp mình.',
    contact_required:'Nhập số điện thoại/Zalo và Gmail để tạo đơn giúp mình.',
    phone_required:  'Nhập Zalo hoặc số điện thoại để tạo đơn giúp mình.',
    email_required:  'Nhập Gmail để tạo đơn giúp mình.',
    email_invalid:   'Gmail chưa đúng định dạng. Kiểm tra lại giúp mình.',
    rate_limited:    'Bạn tạo hơi nhiều đơn. Chờ ít phút rồi thử lại nhé.',
    order_not_found: 'Không tìm thấy mã đơn này. Kiểm tra lại giúp mình.',
    loi_khong_ro:    'Không gọi được máy chủ. Kiểm tra mạng rồi thử lại.'
  };
  var errText = function (e) {
    return ERRS[e && e.message] || ERRS.loi_khong_ro;
  };

  /* --- 7a. Giá và danh sách gói ---
     Máy chủ là nguồn sự thật: bật thêm gói trong trang quản trị là trang này
     tự hiện thêm, KHÔNG phải sửa HTML. Số gói quyết định cách vẽ:

       1 gói  -> giữ nguyên khối in sẵn trong HTML (tấm vé ở trang chủ,
                 thẻ ngang ở trang mua key) — chỉ thay tên và giá
       2 gói+ -> thay bằng lưới thẻ chọn được

     Bản in sẵn trong HTML còn là bản dự phòng: mạng chậm thì trang vẫn có
     giá để hiện, không bao giờ trống trơn.                                */
  var planBox = document.querySelector('[data-plans]');
  var chosen = (new URLSearchParams(location.search).get('plan'))
    || (planBox && planBox.dataset.plan)
    || 'life';
  var PLANS = [];

  if (planBox) {
    shopApi(['/v1/shop/plans', '/v1/plans']).then(function (j) {
      PLANS = (j.plans || []).map(normalPlan);
      if (!PLANS.length) { return; }
      if (!PLANS.filter(function (p) { return p.id === chosen; })[0]) {
        chosen = PLANS[0].id;                 // gói cũ đã tắt bán
      }
      heroPrice(PLANS);
      syncPriceCopy(PLANS);
      if (PLANS.length === 1) { onePlan(PLANS[0]); } else { manyPlans(PLANS); }
    }).catch(function () { /* giữ bản in sẵn trong HTML */ });
  }

  function normalPlan(p) {
    return {
      id: String(p.id || p.name || 'life'),
      name: String(p.name || p.id || 'Vĩnh viễn'),
      price: Number(p.price || 0),
      days: Number(p.days || 0)
    };
  }

  function chosenPlan() {
    return PLANS.filter(function (p) { return p.id === chosen; })[0] || null;
  }

  function shopApi(paths, bodyFor) {
    var i = 0;
    function tryOne() {
      var path = paths[i];
      var body = typeof bodyFor === 'function' ? bodyFor(path) : bodyFor;
      return api(path, body).catch(function (e) {
        i += 1;
        if (i >= paths.length) { throw e; }
        return tryOne();
      });
    }
    return tryOne();
  }

  function syncPriceCopy(plans) {
    var min = Math.min.apply(null, plans.map(function (p) { return p.price; }));
    var text = Number(min).toLocaleString('vi-VN') + 'đ';
    var known = ['200.000đ', '150.000đ'];
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var nodes = [];
    while (walker.nextNode()) { nodes.push(walker.currentNode); }
    nodes.forEach(function (node) {
      known.forEach(function (old) {
        node.nodeValue = node.nodeValue.replaceAll(old, text);
      });
    });

    ['title', 'meta[name="description"]', 'meta[property="og:title"]', 'meta[property="og:description"]'].forEach(function (sel) {
      var el = sel === 'title' ? document.querySelector('title') : document.querySelector(sel);
      if (!el) { return; }
      var attr = sel === 'title' ? 'textContent' : 'content';
      known.forEach(function (old) {
        el[attr] = el[attr].replaceAll(old, text);
      });
    });
  }

  /**
   * Nút hero và ô thống kê ở trang chủ.
   *
   * Một gói thì ghi thẳng giá; nhiều gói thì ghi "từ <giá rẻ nhất>" - để
   * nguyên "150.000đ" khi đang bán 5 gói là nói sai giá với khách.
   */
  function heroPrice(plans) {
    var min = Math.min.apply(null, plans.map(function (p) { return p.price; }));
    var cta = document.querySelector('[data-cta-price]');
    if (cta) {
      cta.textContent = 'Mua key · ' + (plans.length > 1 ? 'từ ' : '')
        + Number(min).toLocaleString('vi-VN') + 'đ';
    }
    var sp = document.querySelector('[data-stat-price]');
    if (sp) {
      sp.dataset.count = String(Math.round(min / 1000));
      sp.textContent = '0';
    }
    var sl = document.querySelector('[data-stat-label]');
    if (sl && plans.length > 1) { sl.textContent = 'giá từ'; }
  }

  /** Một gói: chỉ thay số vào khối đã có sẵn. */
  function onePlan(p) {
    chosen = p.id;
    var price = planBox.querySelector('[data-price]');
    if (price) { price.textContent = Number(p.price).toLocaleString('vi-VN'); }
    var nameEl = planBox.querySelector('[data-plan-name]');
    if (nameEl) { nameEl.textContent = p.name + ' · 1 thiết bị'; }
    setText('[data-sum-plan]', p.name);
    setText('[data-sum-total]', money(p.price));
  }

  /** Nhiều gói: thay khối in sẵn bằng lưới thẻ chọn được. */
  function manyPlans(plans) {
    planBox.className = 'plans' + (planBox.closest('.card') ? ' plans--buy' : '');
    // Nhan phia tren doi theo: "Goi duy nhat" thanh "Chon goi".
    var lab = planBox.previousElementSibling;
    if (lab && lab.classList.contains('label')) { lab.textContent = 'Chọn gói'; }
    planBox.innerHTML = '';
    var buying = !!document.querySelector('[data-create]');   // trang mua key

    plans.forEach(function (p) {
      var el = document.createElement(buying ? 'button' : 'a');
      el.className = 'plan';
      if (buying) { el.type = 'button'; } else { el.href = 'mua-key.html?plan=' + p.id; }
      el.dataset.plan = p.id;
      el.dataset.price = p.price;
      el.dataset.name = p.name;
      el.innerHTML =
        '<div class="plan__head"><span class="label">' + esc(p.name) + '</span></div>'
        + '<div class="plan__price"><b>' + Number(p.price).toLocaleString('vi-VN')
        + '</b><i>Đ</i></div>'
        + '<p class="plan__note">'
        + (p.days ? p.days + ' ngày kể từ lúc kích hoạt' : 'Không bao giờ hết hạn')
        + '</p>';
      if (buying) { el.addEventListener('click', function () { pick(p.id); }); }
      planBox.appendChild(el);
    });
    if (buying) { pick(chosen); }
  }

  function pick(id) {
    var hit = null;
    planBox.querySelectorAll('[data-plan]').forEach(function (x) {
      var on = x.dataset.plan === id;
      x.classList.toggle('is-picked', on);
      if (on) { hit = x; }
    });
    if (!hit) { return; }
    chosen = id;
    setText('[data-sum-plan]', hit.dataset.name);
    setText('[data-sum-total]', money(hit.dataset.price));
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function setText(sel, v) {
    var el = document.querySelector(sel);
    if (el) { el.textContent = v; }
  }
  function step(n) {
    ['plan', 'pay', 'key'].forEach(function (name, i) {
      var el = document.querySelector('[data-step="' + name + '"]');
      if (el) { el.hidden = (i + 1) !== n; }
    });
    document.querySelectorAll('[data-stepper] li').forEach(function (li) {
      li.classList.toggle('is-on', Number(li.dataset.s) <= n);
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /* --- 7b. Tạo đơn --- */
  var createBtn = document.querySelector('[data-create]');
  if (createBtn) {
    createBtn.addEventListener('click', function () {
      if (createBtn.dataset.busy) { return; }
      var phoneInput = document.querySelector('[data-phone]');
      var emailInput = document.querySelector('[data-email]');
      var phone = (phoneInput && phoneInput.value || '').trim();
      var email = (emailInput && emailInput.value || '').trim();
      var phoneField = document.querySelector('[data-phone-field]');
      var emailField = document.querySelector('[data-email-field]');
      var err = document.querySelector('[data-create-err]');
      var emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
      if (phoneField) { phoneField.classList.remove('is-invalid'); }
      if (emailField) { emailField.classList.remove('is-invalid'); }
      if (!phone) {
        if (phoneField) { phoneField.classList.add('is-invalid'); }
        if (err) { err.textContent = ERRS.phone_required; err.hidden = false; }
        if (phoneInput) { phoneInput.focus(); }
        return;
      }
      if (!email) {
        if (emailField) { emailField.classList.add('is-invalid'); }
        if (err) { err.textContent = ERRS.email_required; err.hidden = false; }
        if (emailInput) { emailInput.focus(); }
        return;
      }
      if (!emailOk) {
        if (emailField) { emailField.classList.add('is-invalid'); }
        if (err) { err.textContent = ERRS.email_invalid; err.hidden = false; }
        if (emailInput) { emailInput.focus(); }
        return;
      }
      var contact = phone + ' · ' + email;
      createBtn.dataset.busy = '1';
      document.querySelector('[data-spinner]').hidden = false;
      setText('[data-create-label]', 'Đang tạo đơn…');
      err.hidden = true;

      shopApi(['/v1/shop/order', '/v1/order'], function (path) {
        var p = chosenPlan();
        return {
          plan: path === '/v1/order' && p ? p.name : chosen,
          contact: contact,
          phone: phone,
          email: email
        };
      }).then(function (o) {
        kho.ghi(LS_ORDER, o.code);
        showOrder(o);
        step(2);
        poll(o.code);
      }).catch(function (e) {
        err.textContent = errText(e);
        err.hidden = false;
      }).then(function () {
        createBtn.dataset.busy = '';
        document.querySelector('[data-spinner]').hidden = true;
        setText('[data-create-label]', 'Tạo đơn hàng');
      });
    });
  }

  function showOrder(o) {
    var qr = document.querySelector('[data-qr]');
    if (qr) {
      var qrUrl = o.qr || o.qr_url || '';
      var box = qr.closest('.qr');
      box.classList.toggle('is-empty', !qrUrl);
      qr.src = qrUrl;
    }
    var b = o.bank || {};
    setText('[data-bank-name]', b.name || b.id || '—');
    setText('[data-bank-acc]', b.account || '—');
    setText('[data-bank-owner]', b.owner || '—');
    setText('[data-amount]', money(o.amount));
    var content = o.content || o.code;
    ['[data-order-code]', '[data-order-code2]', '[data-order-code3]'].forEach(function (s) { setText(s, content); });
    if (o.expires_at) { countdown(o.expires_at); }
  }

  function countdown(until) {
    var el = document.querySelector('[data-countdown]');
    if (!el) { return; }
    (function tick() {
      var left = until - Math.floor(Date.now() / 1000);
      if (left <= 0) { el.textContent = 'đã hết hạn'; return; }
      var h = Math.floor(left / 3600), m = Math.floor((left % 3600) / 60);
      el.textContent = h ? h + ' giờ ' + m + ' phút' : m + ' phút';
      setTimeout(tick, 30000);
    })();
  }

  /* --- 7c. Chờ tiền vào ---
     Ba thứ quyết định người mua thấy key NHANH hay phải tự bấm:

     1. NHỊP HỎI. Trước đây giãn dần tới 30 giây, nên admin ghép đơn xong
        khách vẫn ngồi nhìn nửa phút. Nay tối đa 15 giây.
     2. ĐƠN HẾT HẠN KHÔNG ĐƯỢC DỪNG HẲN. Admin vẫn ghép tay được sau đó -
        dừng là trang không bao giờ biết.
     3. QUAY LẠI TAB LÀ HỎI NGAY. Đây mới là chỗ hay gặp nhất: khách bấm sang
        app ngân hàng để chuyển tiền, trình duyệt bóp hoặc treo hẳn đồng hồ
        của tab nền, quay lại thì đồng hồ chưa chạy tiếp. Nghe sự kiện "tab
        hiện lại" và hỏi ngay lúc đó là hết cảnh phải bấm tay.               */
  var polling = null;
  var pollCode = null;
  var lastAsk = 0;

  function poll(code) {
    pollCode = code;
    clearTimeout(polling);
    ask(true);
  }

  function ask(now) {
    if (!pollCode) { return; }
    if (!now && Date.now() - lastAsk < 3000) { return; }   // chống hỏi dồn
    lastAsk = Date.now();
    var code = pollCode;
    shopApi(['/v1/shop/order/' + encodeURIComponent(code), '/v1/order/' + encodeURIComponent(code)]).then(function (o) {
      if (pollCode !== code) { return; }                   // đã sang đơn khác
      if (o.status === 'paid' && o.key) { gotKey(o); return; }
      if (o.status === 'expired') {
        setText('[data-wait-label]', 'Đơn đã hết hạn — nhắn Zalo nếu bạn đã chuyển tiền');
        schedule(60000);                                   // vẫn theo dõi, chậm thôi
        return;
      }
      schedule(Math.min(5000 + (Date.now() - startedAt) / 20, 15000));
    }).catch(function () {
      schedule(10000);
    });
  }

  var startedAt = Date.now();
  function schedule(ms) {
    clearTimeout(polling);
    polling = setTimeout(function () { ask(true); }, ms);
  }

  /* Quay lại tab, hoặc cửa sổ được chọn lại -> hỏi ngay. */
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) { ask(false); }
  });
  window.addEventListener('focus', function () { ask(false); });

  /** Da co key: dung do, hien buoc 3, va bao cho nguoi dang o app khac. */
  function gotKey(o) {
    clearTimeout(polling);
    pollCode = null;
    setText('[data-key]', o.key);
    ['[data-order-code]', '[data-order-code2]', '[data-order-code3]']
      .forEach(function (sel) { setText(sel, o.code); });
    // Doi tieu de tab: nguoi mua thuong dang o app ngan hang, quay ve la thay
    // ngay tren thanh tab ma khong can mo trang len.
    try { document.title = '✅ Key đã sẵn sàng — Cartube'; } catch (e) { }
    step(3);
  }

  var recheck = document.querySelector('[data-recheck]');
  if (recheck) {
    recheck.addEventListener('click', function () {
      var code = document.querySelector('[data-order-code]').textContent.trim();
      if (code && code !== '—') { poll(code); }   // bam tay = hoi ngay lap tuc
    });
  }

  /* --- 7d. Tra cứu đơn cũ: mã đơn chính là "tài khoản" của người mua --- */
  var lookBtn = document.querySelector('[data-lookup-go]');
  if (lookBtn) {
    lookBtn.addEventListener('click', function () {
      var code = (document.querySelector('[data-lookup]').value || '').trim().toUpperCase();
      var msg = document.querySelector('[data-lookup-msg]');
      if (!code) { return; }
      msg.hidden = true;
      shopApi(['/v1/shop/order/' + encodeURIComponent(code), '/v1/order/' + encodeURIComponent(code)]).then(function (o) {
        if (o.status === 'paid' && o.key) { gotKey(o); return; }
        showOrder(o);
        step(2);
        poll(o.code);
      }).catch(function (e) {
        msg.textContent = errText(e);
        msg.hidden = false;
      });
    });

    /* Quay lại trang mà đơn cũ CÒN TREO thì mở lại đúng chỗ đang dở.
       Đơn ĐÃ TRẢ TIỀN thì KHÔNG nhảy vào bước 3: người vào lại trang mua key
       gần như luôn là muốn mua thêm, không phải xem lại key cũ. Trước đây nhảy
       thẳng vào bước 3 nên không còn đường nào về bước 1 để mua tiếp.
       Key cũ vẫn lấy lại được: hiện một dòng nhắc có nút xem, và ô tra cứu
       mã đơn ở dưới vẫn chạy.  */
    var saved = kho.doc(LS_ORDER);
    if (saved) {
      shopApi(['/v1/shop/order/' + encodeURIComponent(saved), '/v1/order/' + encodeURIComponent(saved)]).then(function (o) {
        if (o.status === 'pending') {
          showOrder(o); step(2); poll(o.code);
        } else if (o.status === 'paid' && o.key) {
          showLastOrder(o);
        }
      }).catch(function () {});
    }
  }

  /* Dòng nhắc "đơn gần nhất đã có key" ở đầu bước 1. */
  function showLastOrder(o) {
    var box = document.querySelector('[data-last-order]');
    if (!box) { return; }
    box.hidden = false;
    setText('[data-last-code]', o.code);
    var btn = box.querySelector('[data-last-view]');
    if (btn && !btn.dataset.wired) {
      btn.dataset.wired = '1';
      btn.addEventListener('click', function () { gotKey(o); });
    }
  }

  /* Mua thêm key: về bước 1, xoá sạch dấu vết đơn cũ. */
  var again = document.querySelector('[data-buy-again]');
  if (again) {
    again.addEventListener('click', function () {
      clearTimeout(polling);
      kho.xoa(LS_ORDER);
      var box = document.querySelector('[data-last-order]');
      if (box) { box.hidden = true; }
      var phone = document.querySelector('[data-phone]');
      var email = document.querySelector('[data-email]');
      if (phone) { phone.value = ''; }
      if (email) { email.value = ''; }
      setText('[data-key]', '—');
      step(1);
    });
  }

  /* --- 7e. Chép --- */
  function copier(btnSel, srcSel, done) {
    var btn = document.querySelector(btnSel);
    if (!btn) { return; }
    btn.addEventListener('click', function () {
      var t = document.querySelector(srcSel).textContent.trim();
      if (navigator.clipboard) { navigator.clipboard.writeText(t).catch(function () {}); }
      var old = btn.textContent;
      btn.textContent = done;
      setTimeout(function () { btn.textContent = old; }, 1800);
    });
  }
  copier('[data-copy]', '[data-key]', 'Đã chép');
  copier('[data-copy-code]', '[data-order-code]', 'Đã chép');

  /* --- 9. Nut tai APK ----------------------------------------------
     HOI MAY CHU chu khong ghi cung link: nguoi quan tri tai ban APK moi
     len trang quan tri la trang nay dung ngay, khong phai sua web.

     Van co link du phong ghi cung: neu may chu khong tra loi duoc thi nut van
     tai duoc ban dang co, thay vi tro vao hu khong.                          */
  var APK_DUPHONG = '/downloads/CarTube-com.cartube.carplay-4.1.24.apk';
  var APK_TEN_FILE = 'CarTube-com.cartube.carplay-4.1.24.apk';

  (function () {
    var nut = document.querySelectorAll('[data-apk-link]');
    if (!nut.length) { return; }

    function dat(url, ghiChu) {
      nut.forEach(function (a) {
        a.setAttribute('href', url);
        a.setAttribute('download', APK_TEN_FILE);
        var t = a.querySelector('span') || a;
        t.textContent = 'Tải APK CarTube';
      });
      if (!ghiChu) { return; }
      // Hien phien ban ngay canh nut de khach biet minh dang tai ban nao.
      nut.forEach(function (a) {
        if (a.parentNode.querySelector('[data-apk-ver]')) { return; }
        var s = document.createElement('span');
        s.setAttribute('data-apk-ver', '');
        s.style.cssText = 'display:block;margin-top:8px;font-size:13px;color:#7d736c';
        s.textContent = ghiChu;
        a.parentNode.appendChild(s);
      });
    }

    api('/v1/store/carstore').then(function (d) {
      var mb = (d.size / 1048576).toFixed(1).replace('.', ',');
      dat(d.url, 'Bản ' + d.ver + ' · ' + mb + ' MB'
        + (d.min_android ? ' · cần Android ' + d.min_android + ' trở lên' : ''));
    }).catch(function () {
      dat(APK_DUPHONG, null);
    });
  }());

})();


/* ============================================================
   Menu tren dien thoai
   ------------------------------------------------------------
   Bat/tat class .is-menu tren <header>; CSS lo phan hien. Dong lai khi bam mot
   link, bam ra ngoai, hoac nhan Esc - thieu ba cai do thi menu ket lai tren man
   hinh sau khi chuyen trang bang neo (#) va che mat noi dung.
   ============================================================ */
(function () {
  var header = document.querySelector('.header');
  var nut = header && header.querySelector('.nav-toggle');
  if (!header || !nut) { return; }

  function dat(mo) {
    header.classList.toggle('is-menu', mo);
    nut.setAttribute('aria-expanded', mo ? 'true' : 'false');
    nut.setAttribute('aria-label', mo ? 'Đóng menu' : 'Mở menu');
  }

  nut.addEventListener('click', function (e) {
    e.stopPropagation();
    dat(!header.classList.contains('is-menu'));
  });

  header.addEventListener('click', function (e) {
    if (e.target.closest('.nav a')) { dat(false); }
  });

  document.addEventListener('click', function (e) {
    if (!header.contains(e.target)) { dat(false); }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { dat(false); }
  });

  // Xoay ngang may thanh man hinh rong: CSS hien lai .nav dang hang, nhung class
  // .is-menu con lai se lam nut ba gach thanh dau X vinh vien.
  window.addEventListener('resize', function () {
    if (window.innerWidth > 900) { dat(false); }
  }, { passive: true });
})();


/* --- 10. Tab hướng dẫn cài đặt: APK / CH Play -------------------- */
(function () {
  var root = document.querySelector('[data-install-tabs]');
  if (!root) { return; }
  var tabs = Array.prototype.slice.call(document.querySelectorAll('[data-install-tab]'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('[data-install-panel]'));

  function chon(name, moveFocus) {
    tabs.forEach(function (tab) {
      var on = tab.getAttribute('data-install-tab') === name;
      tab.classList.toggle('is-active', on);
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
      tab.setAttribute('tabindex', on ? '0' : '-1');
      if (on && moveFocus) { tab.focus(); }
    });
    panels.forEach(function (panel) {
      var on = panel.getAttribute('data-install-panel') === name;
      panel.hidden = !on;
      panel.classList.toggle('is-active', on);
    });
  }

  tabs.forEach(function (tab, index) {
    tab.addEventListener('click', function () {
      chon(tab.getAttribute('data-install-tab'), false);
    });
    tab.addEventListener('keydown', function (event) {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') { return; }
      event.preventDefault();
      var next = event.key === 'ArrowRight' ? index + 1 : index - 1;
      if (next < 0) { next = tabs.length - 1; }
      if (next >= tabs.length) { next = 0; }
      chon(tabs[next].getAttribute('data-install-tab'), true);
    });
  });

  chon('chplay', false);
}());


/* --- 11. Nut ngon ngu VI / EN toan trang ------------------------------- */
(function () {
  var supported = { vi: '', en: '/vi/en' };
  function storeGet() {
    try { return localStorage.getItem('ct_lang'); } catch (_) { return null; }
  }
  function storeSet(value) {
    try { localStorage.setItem('ct_lang', value); } catch (_) {}
  }
  var current = storeGet() || 'vi';

  function setCookie(value) {
    var expires = '; expires=Fri, 31 Dec 9999 23:59:59 GMT; path=/';
    document.cookie = 'googtrans=' + value + expires;
    if (location.hostname.indexOf('.') !== -1) {
      document.cookie = 'googtrans=' + value + '; domain=' + location.hostname + expires;
      document.cookie = 'googtrans=' + value + '; domain=.' + location.hostname + expires;
    }
  }

  function clearCookie() {
    var expires = '; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    document.cookie = 'googtrans=' + expires;
    if (location.hostname.indexOf('.') !== -1) {
      document.cookie = 'googtrans=' + expires + '; domain=' + location.hostname;
      document.cookie = 'googtrans=' + expires + '; domain=.' + location.hostname;
    }
  }

  function readCookie() {
    var m = document.cookie.match(/(?:^|; )googtrans=([^;]+)/);
    if (!m) { return ''; }
    try { return decodeURIComponent(m[1]); } catch (_) { return m[1]; }
  }

  function mark(lang) {
    document.querySelectorAll('[data-lang]').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.getAttribute('data-lang') === lang);
      btn.setAttribute('aria-pressed', btn.getAttribute('data-lang') === lang ? 'true' : 'false');
    });
  }

  function findSelect() {
    return document.querySelector('select.goog-te-combo');
  }

  function changeSelect(lang) {
    var select = findSelect();
    if (!select) { return false; }
    select.value = lang === 'en' ? 'en' : '';
    select.dispatchEvent(new Event('change'));
    return true;
  }

  function applyLang(lang, reloadIfNeeded) {
    current = lang === 'en' ? 'en' : 'vi';
    storeSet(current);
    mark(current);

    if (current === 'vi') {
      clearCookie();
      if (reloadIfNeeded) {
        window.location.reload();
      }
      return;
    }

    setCookie(supported[current]);
    if (!changeSelect(current) && reloadIfNeeded) {
      window.location.reload();
    }
  }

  function makeSwitcher() {
    if (document.querySelector('.lang-switch')) { return; }

    var box = document.createElement('div');
    box.className = 'lang-switch notranslate';
    box.setAttribute('translate', 'no');
    box.setAttribute('aria-label', 'Chọn ngôn ngữ');
    box.innerHTML = '<button class="lang-switch__btn" type="button" data-lang="vi" aria-pressed="false">VI</button><button class="lang-switch__btn" type="button" data-lang="en" aria-pressed="false">EN</button>';

    var headerBar = document.querySelector('.header__bar');
    var buyBtn = headerBar && headerBar.querySelector(':scope > .btn');
    if (headerBar && buyBtn) {
      headerBar.insertBefore(box, buyBtn);
    } else if (headerBar) {
      headerBar.appendChild(box);
    } else {
      box.classList.add('lang-switch--floating');
      document.body.appendChild(box);
    }

    box.addEventListener('click', function (event) {
      var btn = event.target.closest('[data-lang]');
      if (!btn) { return; }
      applyLang(btn.getAttribute('data-lang'), true);
    });
    mark(current);
  }

  window.googleTranslateElementInit = function () {
    new google.translate.TranslateElement({
      pageLanguage: 'vi',
      includedLanguages: 'en,vi',
      autoDisplay: false
    }, 'google_translate_element');
    setTimeout(function () { applyLang(current, false); }, 500);
  };

  function loadTranslate() {
    if (document.getElementById('google_translate_element')) { return; }
    var mount = document.createElement('div');
    mount.id = 'google_translate_element';
    mount.className = 'lang-switch__mount notranslate';
    mount.setAttribute('translate', 'no');
    document.body.appendChild(mount);

    var cookie = readCookie();
    if (cookie.indexOf('/vi/en') !== -1) { current = 'en'; }
    if (current === 'en') { setCookie(supported.en); }
    else { clearCookie(); }
    mark(current);

    var script = document.createElement('script');
    script.src = 'https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
    script.async = true;
    document.head.appendChild(script);
  }

  makeSwitcher();
  loadTranslate();
}());


/* --- 12. Gui Gmail tester qua email ------------------------------------ */
(function () {
  document.querySelectorAll('.tester-form[data-mail-to]').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var to = form.getAttribute('data-mail-to') || 'hanoidsc@gmail.com';
      var code = (form.querySelector('input[name="code"]') || {}).value || '';
      var email = (form.querySelector('input[name="email"]') || {}).value || '';
      var subject = 'Mo quyen tai CarTube qua CH Play';
      var body = [
        'Can mo quyen tai CarTube qua CH Play testing.',
        '',
        'Ma don/key: ' + code.trim(),
        'Gmail can mo quyen: ' + email.trim(),
        '',
        'Ghi chu: Gmail tren phai la tai khoan dang dang nhap tren may Android se cai.'
      ].join('\n');
      window.location.href = 'mailto:' + encodeURIComponent(to)
        + '?subject=' + encodeURIComponent(subject)
        + '&body=' + encodeURIComponent(body);
    });
  });
}());
