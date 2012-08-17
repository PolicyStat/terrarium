from setuptools import setup

setup_options = dict(
    name='test_requirement',
    version='0.1.0dev',
    author='Kyle Gibson',
    author_email='kyle.gibson@frozenonline.com',
    description='Test requirement fixture',
    license='BSD',
    url='',
    packages=['test_requirement'],
    long_description='',
    install_requires=[],
    classifiers=[],
    zip_safe=False,
)

setup(**setup_options)
