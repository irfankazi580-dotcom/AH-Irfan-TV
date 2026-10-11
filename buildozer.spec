[app]
title = AH : Irfan
package.name = ahirfan
package.domain = org.irfan
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0.0
requirements = python3,kivy==2.3.0,pyjnius,certifi,android
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 34
android.minapi = 24
android.archs = arm64-v8a
android.ndk = 25b
android.ndk_api = 24
p4a.branch = v2024.01.21
android.accept_sdk_license = True
android.allow_backup = True
android.extra_manifest_application_arguments = ./cleartext.xml

[buildozer]
log_level = 2
warn_on_root = 1
