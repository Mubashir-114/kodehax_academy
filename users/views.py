from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from kodehax_academy.mobile import render_for_device
from .models import User

def home(request):
    return render_for_device(request, "user/base.html")


def _redirect_for_user(user):
    if user.is_superuser or getattr(user, "role", "") == "admin":
        return "adminpanel_dashboard"
    if getattr(user, "role", "") == "teacher":
        return "teacher_dashboard"
    if getattr(user, "role", "") == "student":
        return "student_dashboard"
    return "home"


def _block_cross_role_login(request, target_role):
    if not request.user.is_authenticated:
        return None

    if request.user.is_superuser or request.user.role == "admin":
        return redirect("adminpanel_dashboard")

    if request.user.role == target_role:
        return redirect(_redirect_for_user(request.user))

    messages.error(
        request,
        (
            f"You are already logged in as {request.user.role} in this browser session. "
            "Use Logout first, or open the other role in an incognito window / different browser profile."
        ),
    )
    return redirect(_redirect_for_user(request.user))
# -------------------------
# Student Register
# -------------------------
def student_register(request):

    if request.method == "POST":

        username = request.POST.get("username")
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        if password1 != password2:
            messages.error(request, "Passwords do not match")
            return redirect("student_register")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect("student_register")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists")
            return redirect("student_register")

        User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            role="student"
        )

        messages.success(request, "Student account created successfully")
        return redirect("student_login")

    return render_for_device(request, "user/register/std_register.html", mobile_template_name="mobile/auth/register.html")


# -------------------------
# Teacher Register
# -------------------------
def teacher_register(request):

    if request.method == "POST":

        username = request.POST.get("username")
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        if password1 != password2:
            messages.error(request, "Passwords do not match")
            return redirect("teacher_register")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect("teacher_register")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists")
            return redirect("teacher_register")

        User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            role="teacher"
        )

        messages.success(request, "Teacher account created successfully")
        return redirect("teacher_login")

    return render_for_device(request, "user/register/teacher_register.html")


# -------------------------
# Student Login
# -------------------------
def student_login(request):
    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is None:
            messages.error(request, "Invalid username or password")
            return redirect("student_login")

        if user.role != "student":
            messages.error(request, "This account is not a student account")
            return redirect("student_login")

        login(request, user)
        return redirect("student_dashboard")

    return render_for_device(request, "user/login/std_login.html")


# -------------------------
# Teacher Login
# -------------------------
def teacher_login(request):
    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is None:
            messages.error(request, "Invalid username or password")
            return redirect("teacher_login")

        if user.is_superuser or user.role == "admin":
            login(request, user)
            return redirect("adminpanel_dashboard")

        if user.role != "teacher":
            messages.error(request, "This account is not a teacher or admin account")
            return redirect("teacher_login")

        login(request, user)
        return redirect("/teacher/dashboard/")

    return render_for_device(request, "user/login/teacher_login.html")


def user_logout(request):
    logout(request)
    messages.success(request, "Logged out successfully.")
    return redirect("home")
