from django.conf import settings
from django.core.checks import Error, Warning, register, Tags


@register(Tags.security, deploy=True)
def execution_configuration(app_configs, **kwargs):
    if not settings.PRODUCTION:
        return []
    if settings.CODE_EXECUTION_BACKEND != "remote":
        return [Error("Production must use the remote isolated code executor; the development runner is not a sandbox.",
                      id="code_execution.E001")]
    if not settings.CODE_EXECUTION_URL or not settings.CODE_EXECUTION_TOKEN:
        return [Warning("Production coding execution needs a provisioned isolated HTTPS service and CODE_EXECUTION_URL/TOKEN.",
                        hint="Coding requests return 503 without grading or charging attempts until it is configured.",
                        id="code_execution.W001")]
    return []
