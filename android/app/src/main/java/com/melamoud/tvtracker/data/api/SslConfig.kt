package com.melamoud.tvtracker.data.api

import android.content.Context
import java.io.ByteArrayInputStream
import java.security.KeyStore
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager

data class SslConfig(
    val socketFactory: SSLSocketFactory,
    val trustManager: X509TrustManager,
    val hostnameVerifier: HostnameVerifier,
)

fun buildSslConfig(context: Context, host: String): SslConfig {
    val systemTm = systemTrustManager()
    val extraCerts = loadBundledCerts(context)
    val trustManager = if (extraCerts.isEmpty()) {
        systemTm
    } else {
        CombinedTrustManager(systemTm, extraTrustManager(extraCerts))
    }
    val sslContext = SSLContext.getInstance("TLS")
    sslContext.init(null, arrayOf(trustManager), null)
    val hostnameVerifier = HostnameVerifier { hostname, session ->
        hostname.equals(host, ignoreCase = true) ||
            javax.net.ssl.HttpsURLConnection.getDefaultHostnameVerifier().verify(hostname, session)
    }
    return SslConfig(sslContext.socketFactory, trustManager, hostnameVerifier)
}

private fun systemTrustManager(): X509TrustManager {
    val factory = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
    factory.init(null as KeyStore?)
    return factory.trustManagers.filterIsInstance<X509TrustManager>().first()
}

private fun extraTrustManager(certs: List<X509Certificate>): X509TrustManager {
    val keyStore = KeyStore.getInstance(KeyStore.getDefaultType())
    keyStore.load(null)
    certs.forEachIndexed { index, cert ->
        keyStore.setCertificateEntry("server$index", cert)
    }
    val factory = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
    factory.init(keyStore)
    return factory.trustManagers.filterIsInstance<X509TrustManager>().first()
}

private fun loadBundledCerts(context: Context): List<X509Certificate> {
    return try {
        val pem = context.assets.open("server_cert.pem").bufferedReader().use { it.readText() }
        val factory = CertificateFactory.getInstance("X.509")
        val certs = pem.split("-----END CERTIFICATE-----")
            .map { it.trim() }
            .filter { it.contains("BEGIN CERTIFICATE") }
            .map { chunk ->
                val restored = "$chunk\n-----END CERTIFICATE-----\n"
                factory.generateCertificate(ByteArrayInputStream(restored.toByteArray())) as X509Certificate
            }
        AuthLog.i("Loaded ${certs.size} bundled TLS cert(s) subject=${certs.firstOrNull()?.subjectDN}")
        certs
    } catch (e: Exception) {
        AuthLog.e("No bundled server_cert.pem (or parse failed)", e)
        emptyList()
    }
}

private class CombinedTrustManager(
    private val primary: X509TrustManager,
    private val extra: X509TrustManager,
) : X509TrustManager {
    override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {
        primary.checkClientTrusted(chain, authType)
    }

    override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
        try {
            primary.checkServerTrusted(chain, authType)
        } catch (_: Exception) {
            extra.checkServerTrusted(chain, authType)
        }
    }

    override fun getAcceptedIssuers(): Array<X509Certificate> =
        primary.acceptedIssuers + extra.acceptedIssuers
}
