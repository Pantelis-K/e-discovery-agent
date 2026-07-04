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
    # Resolved participant display (spec §5, added Task-B / identity resolution).
    # Derived at ingest from the raw From/To/Cc via documents.participants; stored as
    # JSON. Each display value is a structured unit {raw, display, kind, cn_code,
    # email, domain}. from_display holds ONE unit (or null); to_/cc_display hold a
    # JSON list of units. Raw from_addr/to_addrs/cc_addrs are kept alongside for audit.
    from_display = models.TextField(null=True, blank=True)   # JSON object or null
    to_display = models.TextField(null=True, blank=True)     # JSON array of units
    cc_display = models.TextField(null=True, blank=True)     # JSON array of units
    
    class Meta:
        pass

    def __str__(self):
        return f"Document {self.doc_id}"
