63:                 format=serialization.PublicFormat.SubjectPublicKeyInfo)
64:         with open(path, 'wb') as f:
65:             f.write(pem)
66:
67:     def sig_type(self):
68:         return "PKCS1_PSS_RSA{}_SHA256".format(self.key_size())
69:
70:     def sig_tlv(self):
71:         return"RSA{}".format(self.key_size())
72:
73:     def sig_len(self):
74:         return self.key_size() / 8
75:
76:     def verify(self, signature, payload):
77:         k = self.key
78:         if isinstance(self.key, rsa.RSAPrivateKey):
79:             k = self.key.public_key()
80:         return k.verify(signature=signature, data=payload,
81:                         padding=PSS(mgf=MGF1(SHA256()), salt_length=32),
82:                         algorithm=SHA256())
83:
84:
