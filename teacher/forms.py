from django import forms
from .models import ClassRoom, TeacherProfile
from student.upload_validation import validate_profile_image


class ClassRoomForm(forms.ModelForm):
    def clean_readme_content(self):
        readme_content = (self.cleaned_data.get("readme_content") or "").strip()
        if not readme_content:
            raise forms.ValidationError("Add the classroom README before creating the class.")
        return readme_content

    class Meta:
        model = ClassRoom
        fields = ["name", "description", "readme_content"]

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "w-full border rounded p-2",
                "placeholder": "e.g. Full Stack Web Development"
            }),

            "description": forms.Textarea(attrs={
                "class": "w-full border rounded p-2",
                "rows": 4,
                "placeholder": "Explain what students will learn, how the class runs, and what to expect."
            }),
            "readme_content": forms.Textarea(attrs={
                "class": "w-full border rounded p-2 font-mono",
                "rows": 16,
                "placeholder": "# Course README\n\nAdd setup steps, learning goals, resources, and weekly structure here..."
            }),
        }


class TeacherProfileForm(forms.ModelForm):
    def clean_profile_picture(self):
        profile_picture = self.cleaned_data.get("profile_picture")
        if profile_picture:
            validate_profile_image(profile_picture)
        return profile_picture

    class Meta:
        model = TeacherProfile
        fields = [
            "profile_picture",
            "full_name",
            "phone_number",
            "department",
            "qualification",
            "years_experience",
            "bio",
            "address",
            "website",
            "linkedin",
        ]

        widgets = {
            "profile_picture": forms.ClearableFileInput(attrs={
                "class": "hidden",
                "accept": "image/*",
            }),
            "full_name": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-zinc-400 bg-white px-3 py-2.5 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400",
                "placeholder": "Full name",
            }),
            "phone_number": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-zinc-400 bg-white px-3 py-2.5 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400",
                "placeholder": "Phone number",
            }),
            "department": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-zinc-400 bg-white px-3 py-2.5 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400",
                "placeholder": "Department / Subject",
            }),
            "qualification": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-zinc-400 bg-white px-3 py-2.5 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400",
                "placeholder": "Qualification",
            }),
            "years_experience": forms.NumberInput(attrs={
                "class": "w-full rounded-xl border border-zinc-400 bg-white px-3 py-2.5 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400",
                "placeholder": "Years of experience",
                "min": 0,
            }),
            "bio": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-zinc-400 bg-white px-3 py-2.5 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400",
                "rows": 4,
                "placeholder": "Short bio",
            }),
            "address": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-zinc-400 bg-white px-3 py-2.5 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400",
                "rows": 3,
                "placeholder": "Address",
            }),
            "website": forms.URLInput(attrs={
                "class": "w-full rounded-xl border border-zinc-400 bg-white px-3 py-2.5 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400",
                "placeholder": "https://your-website.com",
            }),
            "linkedin": forms.URLInput(attrs={
                "class": "w-full rounded-xl border border-zinc-400 bg-white px-3 py-2.5 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-400",
                "placeholder": "https://linkedin.com/in/your-handle",
            }),
        }
