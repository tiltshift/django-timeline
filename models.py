from django.db import models

class StreamItem(models.Model):
    context = models.TextField()
    remove = models.BooleanField()
    clusters = models.ManyToManyField("StreamCluster", related_name="items")

class StreamCluster(models.Model):
    event_type = models.CharField(max_length=64)
    clustered_on = models.CharField(max_length=64)
