int main(void) {
    int n = 5;
    int result = 1;
    while (n > 1) {
        result = result * n;
        n = n - 1;
    }
    if (result == 120) {
        return result;
    } else {
        return 0;
    }
}
