class TenantContextMiddleware:
    """
    Resolves tenant and branch strictly from authenticated server-side state.
    Never trusts unauthenticated or raw client-supplied tenant IDs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_tenant_id = None
        request.active_branch_id = None

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            request.active_tenant_id = getattr(user, "tenant_id", None)
            session_branch = request.session.get("active_branch_id")
            if session_branch:
                request.active_branch_id = session_branch

        return self.get_response(request)