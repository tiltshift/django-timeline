from distutils.core import setup
 
setup(
    name='django-timeline',
    version='0.5',
    description='a Django timeline (activity stream) using redis',
    long_description = open("readme.md").read(),
    author='Chris Drackett',
    author_email='chris@chrisdrackett.com',
    url = "https://dmishe@github.com/shelfworthy/django-timeline.git",
    packages = [
        'timeline',
        'timeline.templatetags',
    ],
    install_requires=[
        'django>=1.3.1',
        'redis>=2.0.0'
    ],
    classifiers = [
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Framework :: Django",
    ]
)