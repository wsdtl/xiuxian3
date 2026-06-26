"""QQ 回调地址验证签名工具。"""

from cryptography.hazmat.primitives.asymmetric import ed25519


def make_validation_signature(bot_secret: str, plain_token: str, event_ts: str) -> str:
    """生成 QQ 回调验证签名。

    QQ 开放平台验证回调地址时会给 plain_token 和 event_ts；服务端用
    Bot Secret 派生 Ed25519 私钥，对 event_ts + plain_token 签名后返回。
    """

    seed = _secret_seed(bot_secret)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
    message = f"{event_ts}{plain_token}".encode("utf-8")
    return private_key.sign(message).hex()


def _secret_seed(bot_secret: str) -> bytes:
    """按 QQ 示例逻辑扩展 Bot Secret，直到 Ed25519 种子达到 32 字节。"""

    secret = bot_secret.strip()
    if not secret:
        raise ValueError("QQ_BOT_SECRET 不能为空")

    seed = secret.encode("utf-8")
    while len(seed) < 32:
        seed += seed
    return seed[:32]
