from app.core.context import RequestContext


def ctx(*perms: str, superuser: bool = False) -> RequestContext:
    return RequestContext(
        user_id=1, is_superuser=superuser, company_id=1, permissions=frozenset(perms)
    )


def test_permission_exacte():
    assert ctx("sales:read").has("sales:read")
    assert not ctx("sales:read").has("sales:write")


def test_joker_module():
    assert ctx("sales:*").has("sales:write")
    assert not ctx("sales:*").has("invoicing:write")


def test_joker_global_et_superuser():
    assert ctx("*").has("n_importe:quoi")
    assert ctx(superuser=True).has("n_importe:quoi")
