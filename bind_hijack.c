/*
 * bind_hijack.c — proot/Android helper.
 *
 * In proot the process has no CAP_NET_BIND_SERVICE, so binding to ports
 * < 1024 fails with EACCES. This shim intercepts libc bind() and silently
 * remaps any privileged port P to P+10000 (e.g. 80 -> 10080, 443 -> 10443).
 *
 * Build:
 *   gcc -shared -fPIC -o bind_hijack.so bind_hijack.c -ldl
 * Use:
 *   LD_PRELOAD=./bind_hijack.so streamforge --serve --port 80
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>

#define OFFSET 10000

typedef int (*real_bind_t)(int, const struct sockaddr *, socklen_t);

static void remap(struct sockaddr *addr) {
    if (addr && addr->sa_family == AF_INET) {
        struct sockaddr_in *s = (struct sockaddr_in *)addr;
        int port = ntohs(s->sin_port);
        if (port > 0 && port < 1024) {
            int newp = port + OFFSET;
            s->sin_port = htons((unsigned short)newp);
            fprintf(stderr,
                    "[bind_hijack] remapped privileged port %d -> %d\n", port, newp);
        }
    }
}

int bind(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    static real_bind_t real = 0;
    if (!real)
        real = (real_bind_t)dlsym(RTLD_NEXT, "bind");

    struct sockaddr_storage copy;
    if (addr && addrlen <= sizeof(copy)) {
        memcpy(&copy, addr, addrlen);
        remap((struct sockaddr *)&copy);
        return real(sockfd, (struct sockaddr *)&copy, addrlen);
    }
    return real(sockfd, addr, addrlen);
}
