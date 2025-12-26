from django.db import models
from apps.aiChat.models import BaseModel
from apps.authentication.models import User
import uuid

class Temple(BaseModel):
    CROWD_LEVEL_CHOISES =[
        ('LOW','Low'),
        ('MEDIUM','Medium'),
        ('High','High'),
        ("VERY_HIGH", "Very High"),
    ]

    temple_id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True,null=True)
    latitude = models.DecimalField(max_digits=9,decimal_places=6)
    longitude = models.DecimalField(max_digits=9,decimal_places=6)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100,default='maharashtra')
    image_url = models.TextField(blank=True,null=True)
    crowd_level  = models.CharField(max_length=10,choices=CROWD_LEVEL_CHOISES,default='LOW')
    crowd_message = models.CharField(max_length=255,blank=True,null=True,help_text="Admin advisory message about crowd level")
    is_active = models.BooleanField(default=True) 


    class Meta:
        db_table = "temples"
        indexes =[
            models.Index(fields=['city']),
            models.Index(fields=['state']),
        ]

    def __str__(self):
        return self.name
    

class TempleAnalyticsView(models.Model):
    Event_Type =[
        ("VIEW", "Viewed temple"),
        ("NAVIGATE", "Navigation started"),
        ("DETAIL_OPEN", "Opened details"),     

    ]

    event_id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    user = models.ForeignKey(User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="temple_events",)
    temple = models.ForeignKey(Temple,on_delete=models.CASCADE,related_name="analytics_events")

    event_type = models.CharField(max_length=20,choices=Event_Type)
    user_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    user_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        db_table = 'temple_analytics_views'
        indexes = [
            models.Index(fields=["temple", "event_type"]),
            models.Index(fields=["created_at"]),
        ]
    
