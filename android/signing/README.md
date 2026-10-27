# Signing key

`release.p12` is the key that signs every published build of the phone app, so
each new version installs as an update over the last.

The file is encrypted (AES-256, PKCS#12) with a random 43-character password.
That password is stored only as the `HH_KEYSTORE_PASSWORD` secret in this
repository's GitHub settings; without it the file is useless.

If the password is ever lost: make a new key, uninstall the app, install the
new build, and set it up again (Home Assistant keeps all the data).
