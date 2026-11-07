// Euclid's algorithm: gcd(35, 64) = 1.
// Negative inputs are normalized; gcd(0, 0) returns 0 by convention.
int main(void) {
    int a = 35;
    int b = 64;

    if (a < 0) {
        a = -a;
    }
    if (b < 0) {
        b = -b;
    }

    while (b != 0) {
        int remainder = a % b;
        a = b;
        b = remainder;
    }

    return a;
}
