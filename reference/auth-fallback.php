<?php
/**
 * Plugin Name: GreenLight auth fallback
 * Description: Restores an application password the web server stripped from Authorization.
 * Version: 1.0.0
 *
 * Drop this file in wp-content/mu-plugins/. Apache CGI/FastCGI and some
 * LiteSpeed setups do not hand Authorization to PHP (RFC 3875). scripts/wp_api.py
 * sends the same Basic credential on X-Greenlight-Authorization, which those
 * servers leave alone. This copies it back to the variables WordPress reads
 * before authentication runs.
 *
 * Does nothing when Authorization already arrived, or when the fallback header
 * is missing or not well-formed Basic. Disable with:
 *   define( 'GREENLIGHT_DISABLE_AUTH_FALLBACK', true );
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

if ( defined( 'GREENLIGHT_DISABLE_AUTH_FALLBACK' ) && GREENLIGHT_DISABLE_AUTH_FALLBACK ) {
	return;
}

$greenlight_already = array(
	'HTTP_AUTHORIZATION',
	'REDIRECT_HTTP_AUTHORIZATION',
	'PHP_AUTH_USER',
	'PHP_AUTH_PW',
);
foreach ( $greenlight_already as $key ) {
	if ( ! empty( $_SERVER[ $key ] ) ) { // phpcs:ignore WordPress.Security.ValidatedSanitizedInput
		return;
	}
}

$header = isset( $_SERVER['HTTP_X_GREENLIGHT_AUTHORIZATION'] )
	? $_SERVER['HTTP_X_GREENLIGHT_AUTHORIZATION']
	: '';
if ( ! is_string( $header ) || ! preg_match( '#^Basic [A-Za-z0-9+/=]+$#', $header ) ) {
	return;
}

$decoded = base64_decode( substr( $header, 6 ), true );
if ( ! is_string( $decoded ) || false === strpos( $decoded, ':' ) ) {
	return;
}
list( $user, $pass ) = explode( ':', $decoded, 2 );
if ( '' === $user || '' === $pass ) {
	return;
}

$_SERVER['HTTP_AUTHORIZATION'] = $header;
$_SERVER['PHP_AUTH_USER']      = $user;
$_SERVER['PHP_AUTH_PW']        = $pass;
