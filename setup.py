from setuptools import setup, find_packages
 
setup(
    name='django-timeline',
    version='0.5',
    description='a Django timeline (activity stream) using redis',
    author='Chris Drackett',
    author_email='chris@tiltshiftstudio.com',
    url = "https://github.com/tiltshift/django-timeline.git",
    packages = find_packages(),
    include_package_data=True,
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