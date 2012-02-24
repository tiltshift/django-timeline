from distutils.core import setup
 
setup(
    name='django-events',
    version='1.0',
    description='Django events using redis',
    long_description = open("readme.md").read(),
    author='Chris Drackett',
    author_email='drackett@mac.com',
    url = "https://dmishe@github.com/shelfworthy/django-events.git",
    packages = [
        'djevents',
        'djevents.templatetags',
    ],
    install_requires=[
        'django>=1.3.1',
        'redis>=2.0.0'
    ],
    classifiers = [
        "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Framework :: Django",
    ]
)
