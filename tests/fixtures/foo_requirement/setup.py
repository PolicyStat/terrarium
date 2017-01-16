from setuptools import setup

setup_options = dict(
    name='foo_requirement',
    version='0.1.0dev',
    author='Kyle Gibson',
    author_email='kyle.gibson@frozenonline.com',
    description='Another test requirement fixture',
    license='BSD',
    url='',
    packages=['foo_requirement'],
    long_description='',
    install_requires=['test_requirement'],
    classifiers=[],
    zip_safe=False,
)

setup(**setup_options)
