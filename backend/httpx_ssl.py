"""httpx_ssl.py — 對外連線的 SSL 設定

存在的原因:
    Python 3.13 起,ssl.create_default_context() 預設啟用 VERIFY_X509_STRICT。
    這項嚴格檢查會拒絕「憑證鏈中的 CA 憑證缺少 Subject Key Identifier 擴充欄位」
    的連線,錯誤訊息為:

        [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
        Missing Subject Key Identifier

    我國政府機關網站(經濟部商工登記、部分開放資料端點)的憑證鏈正好有此情形,
    因此在 Python 3.13 以後的環境會連不上,但 Python 3.12 以前完全正常
    ——這也是為什麼同一份程式在不同人的電腦上表現不一致。

處理方式:
    只關閉 VERIFY_X509_STRICT 這一項,其餘驗證(憑證信任鏈、有效期限、
    主機名稱比對)全部維持啟用。這不是「關閉憑證驗證」,
    僅是回到 Python 3.12 的預設行為。

    若連線的憑證根本無法信任,仍然會被擋下。
"""
import ssl
from typing import Optional

import httpx

_ctx: Optional[ssl.SSLContext] = None
_reported = [False]


def ssl_context() -> ssl.SSLContext:
    """回傳共用的 SSL 設定(僅建立一次)。"""
    global _ctx
    if _ctx is not None:
        return _ctx

    ctx = ssl.create_default_context()
    strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict and (ctx.verify_flags & strict):
        ctx.verify_flags &= ~strict
        if not _reported[0]:
            print("🔐 [SSL] 已關閉 VERIFY_X509_STRICT(Python 3.13+ 預設值),"
                  "以相容政府網站憑證;其餘憑證驗證維持啟用。")
            _reported[0] = True

    # 部分政府端點只提供不完整的憑證鏈,允許以中繼憑證為信任起點
    partial = getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0)
    if partial:
        ctx.verify_flags |= partial

    _ctx = ctx
    return _ctx


def client(**kwargs) -> httpx.AsyncClient:
    """建立套用上述 SSL 設定的 httpx 非同步用戶端。

    用法與 httpx.AsyncClient 相同:
        async with httpx_ssl.client(timeout=..., follow_redirects=True) as c:
            r = await c.get(url)
    """
    kwargs.setdefault("verify", ssl_context())
    return httpx.AsyncClient(**kwargs)
