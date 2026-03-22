from django import forms
from .models import PlatformSettings

class PlatformSettingsForm(forms.ModelForm):
    class Meta:
        model = PlatformSettings
        fields = [
            'platform_name',
            'support_email',
            'require_email_verification',
            'enable_otp_login',
            'max_login_attempts',
            'challenge_time_limit_minutes',
            'auto_generate_challenges',
            'daily_challenge_base_points',
            'hint_cost_penalty',
            'enable_chat_memory',
            'chat_memory_duration',
            'max_messages_per_session',
        ]
