from django.db import models


class Document(models.Model):
    doc_id = models.CharField(max_length=255, primary_key=True)
    x_sdoc = models.CharField(max_length=255, null=True, blank=True)
    x_zlid = models.CharField(max_length=255, null=True, blank=True)
    message_id = models.CharField(max_length=255, null=True, blank=True)
    thread_id = models.CharField(max_length=255, null=True, blank=True)
    subject = models.TextField(null=True, blank=True)
    from_addr = models.CharField(max_length=255, null=True, blank=True)
    to_addrs = models.TextField(null=True, blank=True)
    cc_addrs = models.TextField(null=True, blank=True)
    bcc_addrs = models.TextField(null=True, blank=True)
    date = models.DateTimeField(null=True, blank=True)
    body = models.TextField(null=True, blank=True)
    custodian = models.CharField(max_length=255, null=True, blank=True)
    attachment_refs = models.TextField(null=True, blank=True)
    raw_headers = models.TextField(null=True, blank=True)

    class Meta:
        pass

    def __str__(self):
        return f"Document {self.doc_id}"
