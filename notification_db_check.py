from notifications.models import Notification
from django.contrib.auth import get_user_model

User = get_user_model()

print("==== المستخدمون المرتبطون بالإشعارات ====")
for n in Notification.objects.all():
    print(f"ID: {n.id} | recipient: {getattr(n.recipient, 'username', n.recipient_id)} | title: {n.title} | is_read: {n.is_read} | created_at: {n.created_at}")

print("==== المستخدمون في النظام ====")
for u in User.objects.all():
    print(f"ID: {u.id} | username: {u.username} | email: {u.email}")
