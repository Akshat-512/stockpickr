import hashlib

timestamp = "2025-05-19T15:35:14.000Z"
secret_key = "@28j62#384B1x1w7`B053^a751646962"
data = ""
checksum_input = timestamp + data + secret_key
checksum = hashlib.sha256(checksum_input.encode()).hexdigest()
print(checksum)
